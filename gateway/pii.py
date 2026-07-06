"""PiiEngine: role-preserving sanitize, output-scan, and rehydrate — the
gateway-side glue over core/detect + core/policy + core/vault.

Replaces monoai_gateway/pii.py's PiiGuard, which wrapped SENTINEL's
Pipeline as a black box. Here the three core/ layers are composed
directly, per-message (not collapsed into one synthetic user message —
that workaround is retired now that session_tokens.py makes token IDs
value-deterministic, see DECISIONS.md / G8).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from contracts.policy import Action
from contracts.spans import TextUnit, TextUnitLocator
from detect.pipeline import DetectionPipeline
from policy.engine import evaluate
from policy.schema import Policy
from vault.session_tokens import TOKEN_PREFIX, derive_session_key, make_token_id
from vault.storage.base import VaultStore

_TOKEN_RE = re.compile(r"\[" + re.escape(TOKEN_PREFIX) + r"([0-9a-f]{10})\]")

# Ported from monoai_gateway/orchestrator.py: some models otherwise read
# SENTINEL's own "preserve every PII_TOKEN placeholder" instruction plus a
# sensitive-sounding request as a cue to refuse. Kept short and only added
# when at least one token was actually minted -- a longer notice on every
# request would silently push simple prompts into higher difficulty tiers.
_NON_SENSITIVE_TOKEN_NOTICE = (
    "Note: PII_TOKEN is the real value. Answer directly and helpfully; "
    "never ask for it or call the message incomplete."
)


class BlockedContentError(Exception):
    """BLOCK-classified content is present; rejected before the router/LLM
    ever see it. BLOCK spans are tokenized in the sanitized text but never
    vaulted -- they could never be rehydrated back out anyway."""

    def __init__(self, labels: list[str], session_id: str, span_counts_by_label: dict[str, int]) -> None:
        super().__init__(f"blocked content present: {', '.join(labels)}")
        self.labels = labels
        self.session_id = session_id
        self.span_counts_by_label = span_counts_by_label
        self.audit_record: Any = None


@dataclass
class SanitizeResult:
    messages: list[Any]  # router.contracts.Message, role-preserving
    token_ids: set[str] = field(default_factory=set)
    span_counts_by_label: dict[str, int] = field(default_factory=dict)
    redacted_count: int = 0


class PiiEngine:
    def __init__(self, pipeline: DetectionPipeline, vault: VaultStore, server_secret: str) -> None:
        self._pipeline = pipeline
        self._vault = vault
        self._server_secret = server_secret

    def _session_key(self, session_id: str) -> bytes:
        return derive_session_key(session_id, self._server_secret)

    def sanitize_messages(self, messages: list[Any], session_id: str, policy: Policy) -> SanitizeResult:
        from router.contracts import Message  # local import avoids a hard gateway<->router cycle at module load

        session_key = self._session_key(session_id)
        sanitized_messages: list[Message] = []
        token_ids: set[str] = set()
        span_counts: dict[str, int] = {}
        blocked_labels: set[str] = set()
        redacted_count = 0

        for turn_index, msg in enumerate(messages):
            if not isinstance(msg.content, str):
                sanitized_messages.append(msg)
                continue

            unit = TextUnit(
                unit_id=f"m{turn_index}", role=msg.role, text=msg.content,
                locator=TextUnitLocator(surface="chat_message", path=f"messages[{turn_index}].content"),
                turn_index=turn_index, direction="input",
            )
            spans = self._pipeline.run([unit])
            decisions = evaluate(spans, policy)

            for d in decisions:
                span_counts[d.span.label.value] = span_counts.get(d.span.label.value, 0) + 1
                if d.action == Action.BLOCK:
                    blocked_labels.add(d.span.label.value)

            sanitized_text, minted = self._apply_tokens(msg.content, decisions, session_key, session_id, vault_write=True)
            token_ids |= minted
            redacted_count += sum(1 for d in decisions if d.action == Action.REVERSIBLE)

            sanitized_messages.append(Message(
                role=msg.role, content=sanitized_text, tool_call_id=msg.tool_call_id, name=msg.name,
            ))

        if blocked_labels:
            raise BlockedContentError(sorted(blocked_labels), session_id, span_counts)

        if token_ids:
            sanitized_messages.insert(0, Message(role="system", content=_NON_SENSITIVE_TOKEN_NOTICE))

        return SanitizeResult(
            messages=sanitized_messages, token_ids=token_ids,
            span_counts_by_label=span_counts, redacted_count=redacted_count,
        )

    def scan_output(
        self, text: str, session_id: str, policy: Policy, include_ner: bool = True
    ) -> tuple[str, set[str]]:
        """Output-side scan (G5): runs the SAME detection pipeline over raw
        model output, before rehydration, so PII the model leaked (never
        present in the prompt) is caught too.

        Existing `[PII_TOKEN_xxxxxxxxxx]` placeholders are protected from
        re-detection: the ONNX NER model can misclassify bracket+hex-digit
        syntax as NEARBYGPSCOORDINATE (-> ADDRESS) -- unlike the anchored
        regex/secrets detectors, it's a fuzzy pattern matcher and can
        false-positive on a token that merely looks GPS-coordinate-shaped.
        Without this guard a single legitimate token could be split into
        two overlapping spans and independently re-tokenized, corrupting
        the placeholder.

        `include_ner=False` (used by gateway/streaming.py's per-chunk
        scanning) skips the NER stage entirely: on tiny out-of-context
        flush-window fragments the model can hallucinate entities from a
        few characters (e.g. "mple", a mid-word fragment of "[simple]",
        was once misclassified this way) -- regex/secrets stay reliable
        at any window size since they're anchored patterns, not a fuzzy
        classifier."""
        session_key = self._session_key(session_id)
        protected_ranges = [m.span() for m in _TOKEN_RE.finditer(text)]

        unit = TextUnit(
            unit_id="output", role="assistant", text=text,
            locator=TextUnitLocator(surface="chat_message", path="output"),
            turn_index=0, direction="output",
        )
        spans = self._pipeline.run([unit], include_ner=include_ner)
        decisions = evaluate(spans, policy)
        decisions = [
            d for d in decisions
            if not any(d.span.start < end and start < d.span.end for start, end in protected_ranges)
        ]

        ordered = sorted(decisions, key=lambda d: d.span.start)
        out: list[str] = []
        last_end = 0
        new_token_ids: set[str] = set()
        for d in ordered:
            span = d.span
            if span.start < last_end:
                continue
            out.append(text[last_end:span.start])
            if d.action == Action.BLOCK:
                out.append(f"[REDACTED_OUTPUT_{span.label.value}]")
            elif d.action == Action.REVERSIBLE:
                token_id = make_token_id(session_key, span.text)
                out.append(f"[{TOKEN_PREFIX}{token_id}]")
                self._vault.write_async(session_id, token_id, span.text)
                new_token_ids.add(token_id)
            else:
                out.append(span.text)
            last_end = span.end
        out.append(text[last_end:])
        return "".join(out), new_token_ids

    def strip_tokens_for_classification(self, text: str) -> str:
        """The bracketed token embeds hex digits (0-9a-f mixed), which
        trips difficulty-classifier heuristics that count digit-density
        (e.g. "is this a math word problem?") -- something the old
        decimal-counter token format (a single short digit run) didn't do.
        Router-tier classification should reflect the user's actual
        message, not an artifact of how many PII spans got tokenized, so
        each token is replaced with a neutral single word before
        classify_difficulty runs. The real tokens are untouched in the
        text actually sent to the provider."""
        return _TOKEN_RE.sub("REDACTED", text)

    def rehydrate(
        self, text: str, session_id: str, input_token_ids: set[str], output_token_ids: set[str]
    ) -> tuple[str, list[str], bool]:
        unresolved: list[str] = []

        def _sub(m: re.Match) -> str:
            token_id = m.group(1)
            if token_id in output_token_ids:
                return m.group(0)  # intentional containment -- an output-side leak, stays tokenized
            if token_id in input_token_ids:
                value = self._vault.get(session_id, token_id)
                if value is not None:
                    return value
            unresolved.append(token_id)
            return "[UNRESOLVED_PII_TOKEN]"

        final_text = _TOKEN_RE.sub(_sub, text)
        return final_text, unresolved, bool(unresolved)

    def _apply_tokens(
        self, text: str, decisions: list, session_key: bytes, session_id: str, vault_write: bool
    ) -> tuple[str, set[str]]:
        ordered = sorted(decisions, key=lambda d: d.span.start)
        out: list[str] = []
        last_end = 0
        minted: set[str] = set()
        for d in ordered:
            span = d.span
            if span.start < last_end:
                continue
            out.append(text[last_end:span.start])
            if d.action in (Action.REVERSIBLE, Action.BLOCK):
                token_id = make_token_id(session_key, span.text)
                out.append(f"[{TOKEN_PREFIX}{token_id}]")
                if d.action == Action.REVERSIBLE and vault_write:
                    self._vault.write_async(session_id, token_id, span.text)
                    minted.add(token_id)
                # BLOCK: token generated but never vaulted -- can never be rehydrated.
            else:
                out.append(span.text)
            last_end = span.end
        out.append(text[last_end:])
        return "".join(out), minted
