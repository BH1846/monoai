"""Thin async wrapper over pii_pipeline.Pipeline.

Pipeline.sanitize/complete are synchronous -- SENTINEL-2.0's own "genuinely
async" vault write is a background-thread implementation detail, but the
Python call itself blocks until spans are detected/classified/tokenized.
Every call here goes through asyncio.to_thread so the FastAPI event loop is
never blocked on CPU-bound span detection or the vault's SQLite writes.

This module owns no vault of its own -- SENTINEL is the single vault owner
(see repo root README, "what's simplified"). `token_map` is the handshake
between sanitize() and complete() and must be carried by the caller across
the request lifecycle (it is not persisted anywhere by this wrapper).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from pii_pipeline.pipeline import Pipeline, RehydrationReviewRequired
from pii_pipeline.rampart import RampartPipeline
from pii_pipeline.rampart.minilm import DEFAULT_MODEL_PATH, MiniLMNER
from pii_pipeline.rehydrate import extract_token_ids
from pii_pipeline.rehydrate import rehydrate as _rehydrate_fn
from pii_pipeline.types import AuditLog, Classification, ClassifiedSpan

__all__ = ["PiiGuard", "SanitizeOutcome", "RehydrationReviewRequired"]


@dataclass
class SanitizeOutcome:
    sanitized_prompt: str
    session_id: str
    token_map: Dict[str, ClassifiedSpan]
    audit_log: AuditLog
    blocked_labels: List[str]

    @property
    def blocked(self) -> bool:
        return bool(self.blocked_labels)


class PiiGuard:
    """Async-safe wrapper around one Pipeline (one vault) instance.

    One PiiGuard is meant to be constructed once per process (it owns the
    Vault's SQLite connection and Valkey client) and shared across requests.
    """

    def __init__(self, vault_storage_path: str = "./pii_vault.sqlite", use_onnx_ner: bool = True):
        # RampartPipeline()/MiniLMNER() default to model_path=None, which
        # *always* selects the rule-based fallback tagger even if
        # onnxruntime/tokenizers are installed -- the ONNX model is opt-in
        # per SENTINEL's own design (see rampart/minilm.py MiniLMNER
        # docstring). The rule-based fallback's PERSON-name heuristic
        # requires a capitalized cue ("hello my name is deepak" is missed;
        # "Deepak" is caught), so we opt into the real model here by
        # default. MiniLMNER falls back to rule-based automatically (with a
        # logged warning) if the ONNX model/runtime aren't actually available.
        model_path = DEFAULT_MODEL_PATH if use_onnx_ner else None
        rampart = RampartPipeline(ner=MiniLMNER(model_path=model_path))
        self._pipeline = Pipeline(vault_storage_path=vault_storage_path, rampart=rampart)

    async def sanitize(self, text: str, session_id: Optional[str] = None) -> SanitizeOutcome:
        result = await asyncio.to_thread(self._pipeline.sanitize, text, session_id)

        # BLOCK spans ARE tokenized into sanitized_prompt (never left in
        # plaintext) but are never vaulted, so they can never be rehydrated.
        # Detect them here, at sanitize-time, so the orchestrator can reject
        # the request before it ever reaches the router/LLM.
        blocked_labels = sorted(
            {
                cs.span.label.value
                for cs in result.token_map.values()
                if cs.classification == Classification.BLOCK
            }
        )

        return SanitizeOutcome(
            sanitized_prompt=result.sanitized_prompt,
            session_id=result.session_id,
            token_map=result.token_map,
            audit_log=result.audit_log,
            blocked_labels=blocked_labels,
        )

    async def complete(
        self,
        llm_output: str,
        session_id: str,
        token_map: Dict[str, ClassifiedSpan],
        audit_log: Optional[AuditLog] = None,
    ) -> Tuple[str, List[str], Optional[AuditLog]]:
        """Rehydrate `llm_output` back to original PII values.

        Raises `RehydrationReviewRequired` (re-exported from pii_pipeline)
        if a vaulted token never came back at all, or the model didn't reuse
        the *same set* of placeholders it was given. Callers should catch
        it: `err.final_text` / `err.unresolved` / `err.audit_log` are
        populated so the caller can still return a best-effort response and
        audit it.
        """
        try:
            return await asyncio.to_thread(
                self._pipeline.complete, llm_output, session_id, token_map, audit_log
            )
        except RehydrationReviewRequired:
            # Pipeline.complete() flags ANY placeholder-count mismatch as
            # review-required, including a model simply reusing the same
            # placeholder more than once (e.g. addressing someone by name
            # twice in one reply). That's not actually ambiguous -- every
            # repeat of a given token_id resolves to the same vaulted
            # value. Detect that specific, safe pattern (the set of
            # placeholders used is exactly the set issued -- nothing
            # missing, nothing unknown/hallucinated -- just a different
            # occurrence count) and rehydrate anyway via the same
            # rehydrate() function Pipeline.complete() uses internally,
            # rather than surfacing review_required for something that
            # isn't actually ambiguous. Any other mismatch (missing or
            # unknown tokens) still raises.
            raw_ids = extract_token_ids(llm_output)
            if set(raw_ids) == set(token_map.keys()):
                final_text, unresolved = await asyncio.to_thread(
                    _rehydrate_fn, llm_output, session_id, self._pipeline.vault, token_map
                )
                if audit_log is not None:
                    audit_log.raw_token_ids = raw_ids
                    audit_log.unresolved_tokens = unresolved
                    audit_log.tokens_found = len(token_map) - len(unresolved)
                    audit_log.missing_tokens = len(unresolved)
                    audit_log.missing_token_ids = unresolved
                    audit_log.review_required = bool(unresolved)
                return final_text, unresolved, audit_log
            raise

    async def close(self) -> None:
        await asyncio.to_thread(self._pipeline.close)
