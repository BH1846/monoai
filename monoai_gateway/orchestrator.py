"""orchestrator.py -- the reduced MonoAI request flow:

  request -> scan/redact PII (SENTINEL) -> select model (router) -> call LLM
          -> rehydrate PII into response -> audit log -> return

Steps implemented here (see repo root README for what's real vs stubbed):
  1. Normalize incoming payload, collect its text (reuses the router's
     RequestNormalizer -- the same normalizer LiteRouter.route() uses
     internally -- so format detection stays in one place).
  2. Scan/redact -- PiiGuard.sanitize(text). Any BLOCK-classified span
     rejects the request; the provider never sees the sanitized_prompt.
  3. Select model + call LLM -- LiteRouter.route(...) on the sanitized text.
     The provider only ever receives redacted/tokenized text.
  4. Rehydrate -- PiiGuard.complete(...). A token-count mismatch or a token
     the vault can't resolve does not fail the request -- it's surfaced via
     `review_required` / `unresolved_tokens` on the result and audit record.
  5. Audit -- caller (app.py) writes the returned audit_record off the
     response path via a BackgroundTask.
  6. Return content (OpenAI-compatible shaping happens in app.py).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from monoai_router.contracts import Message
from monoai_router.hot_path.normalizer import RequestNormalizer
from monoai_router.lite.router import LiteRouter

from .audit import AuditLogger
from .pii import PiiGuard, RehydrationReviewRequired


class BlockedContentError(Exception):
    """Raised when the prompt contains BLOCK-classified content (credit
    card / gov ID / secret). The request is rejected before it ever reaches
    the router or the LLM -- BLOCK spans are tokenized in the sanitized
    prompt but deliberately never vaulted, so they could never come back
    rehydrated anyway (see pii_pipeline/rehydrate.py)."""

    def __init__(self, labels: list[str], session_id: str, audit_record: dict[str, Any]):
        self.labels = labels
        self.session_id = session_id
        self.audit_record = audit_record
        super().__init__(f"blocked content present: {', '.join(labels)}")


_NON_SENSITIVE_TOKEN_NOTICE = (
    "Note: PII_TOKEN is the real value. Answer directly and helpfully; "
    "never ask for it or call the message incomplete."
)


@dataclass
class ChatResult:
    request_id: str
    session_id: str
    content: str
    model_id: str
    provider: str
    difficulty: Optional[str]
    usage: dict
    unresolved_tokens: list
    review_required: bool
    sanitized_prompt: str = ""
    raw_model_output: str = ""
    audit_record: dict[str, Any] = field(default_factory=dict)


class Orchestrator:
    def __init__(self, pii: PiiGuard, router: LiteRouter, audit: AuditLogger):
        self._pii = pii
        self._router = router
        self._audit = audit
        self._normalizer = RequestNormalizer()

    async def chat(self, raw_payload: dict[str, Any]) -> ChatResult:
        request_id = str(uuid.uuid4())
        t_start = time.monotonic()

        # 1. Normalize incoming payload, collect all message text.
        ctx = self._normalizer.normalize(raw_payload)
        text = _collect_text(ctx.messages)

        # 2. Scan/redact.
        t0 = time.monotonic()
        sanitize_out = await self._pii.sanitize(text)
        pii_sanitize_ms = (time.monotonic() - t0) * 1000.0

        if sanitize_out.blocked:
            record = {
                "request_id": request_id,
                "session_id": sanitize_out.session_id,
                "event": "blocked",
                "blocked_labels": sanitize_out.blocked_labels,
                "span_counts_by_label": sanitize_out.audit_log.span_counts_by_label,
                "pii_sanitize_ms": round(pii_sanitize_ms, 3),
                "total_ms": round((time.monotonic() - t_start) * 1000.0, 3),
            }
            raise BlockedContentError(sanitize_out.blocked_labels, sanitize_out.session_id, record)

        # 3. Select model + call LLM. Route on the *sanitized* text only --
        # the provider never sees raw PII. Multi-turn structure is
        # collapsed into a single message here; see README "what's
        # simplified" -- SENTINEL's token contract is per-call, so all
        # message text is sanitized together in one sanitize() call to
        # avoid token_id collisions across messages.
        #
        # When at least one token was actually inserted, a short leading
        # system message reassures the model the [PII_TOKEN_xxxx] markers
        # are inert placeholders from an upstream redaction system, not real
        # sensitive data -- some models otherwise read SENTINEL's own
        # "preserve every PII_TOKEN placeholder" instruction plus a
        # sensitive-sounding request (health, legal, ...) as a cue to
        # refuse. Kept deliberately short and added only when needed:
        # LiteRouter's difficulty classifier is a plain word-count heuristic
        # over ALL messages (system included) -- a longer notice on every
        # request would silently push simple prompts into higher tiers.
        messages: list[dict[str, str]] = []
        if sanitize_out.token_map:
            messages.append({"role": "system", "content": _NON_SENSITIVE_TOKEN_NOTICE})
        messages.append({"role": "user", "content": sanitize_out.sanitized_prompt})
        router_payload = {"messages": messages}
        t1 = time.monotonic()
        response = await self._router.route(router_payload)
        router_ms = (time.monotonic() - t1) * 1000.0

        # 4. Rehydrate.
        t2 = time.monotonic()
        review_required = False
        try:
            final_text, unresolved, _ = await self._pii.complete(
                response.content, sanitize_out.session_id, sanitize_out.token_map, sanitize_out.audit_log
            )
        except RehydrationReviewRequired as err:
            review_required = True
            unresolved = list(err.unresolved)
            final_text = err.final_text if err.final_text is not None else response.content
        pii_rehydrate_ms = (time.monotonic() - t2) * 1000.0

        total_ms = (time.monotonic() - t_start) * 1000.0

        # 5. Build the audit record (app.py schedules the actual write off
        # the response path via a BackgroundTask).
        record = {
            "request_id": request_id,
            "session_id": sanitize_out.session_id,
            "event": "completed",
            "difficulty": response.difficulty,
            "model_id": response.model_id,
            "provider": response.provider,
            "span_counts_by_label": sanitize_out.audit_log.span_counts_by_label,
            "redacted_count": len(sanitize_out.token_map),
            "unresolved_tokens": unresolved,
            "review_required": review_required,
            "pii_sanitize_ms": round(pii_sanitize_ms, 3),
            "router_ms": round(router_ms, 3),
            "pii_rehydrate_ms": round(pii_rehydrate_ms, 3),
            "total_ms": round(total_ms, 3),
            "usage": response.usage,
        }

        # 6. Return.
        return ChatResult(
            request_id=request_id,
            session_id=sanitize_out.session_id,
            content=final_text,
            model_id=response.model_id,
            provider=response.provider,
            difficulty=response.difficulty,
            usage=response.usage,
            unresolved_tokens=unresolved,
            review_required=review_required,
            sanitized_prompt=sanitize_out.sanitized_prompt,
            raw_model_output=response.content,
            audit_record=record,
        )


def _collect_text(messages: list[Message]) -> str:
    parts: list[str] = []
    for msg in messages:
        if isinstance(msg.content, str):
            parts.append(msg.content)
        else:
            for part in msg.content:
                if part.type == "text" and part.text:
                    parts.append(part.text)
    return "\n".join(parts)
