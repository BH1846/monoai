"""The 6-step spine (normalize -> sanitize -> route -> call -> rehydrate ->
audit) rebuilt against the new core/ modules. Same shape as
monoai_gateway/orchestrator.py, but role-preserving per-message sanitize
(no more collapsing all messages into one synthetic user message -- that
workaround is retired now that session_tokens.py makes tokens
value-deterministic, see DECISIONS.md / G8), plus output-scan (G5) before
rehydration, and audit records citing policy_id/policy_version/detector
versions and fallback-chain/circuit info.

`chat()` is the non-streaming path (one-shot output-scan+rehydrate).
`prepare_dispatch()` + `finalize_stream()` split the same normalize ->
sanitize -> route prefix out for the streaming path (gateway/api/chat.py),
which needs the RAW provider content fed incrementally through
gateway/streaming.py's StreamRehydrator rather than processed in one shot.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from audit.chain import AuditChain
from contracts.audit import AuditRecord
from pii import BlockedContentError, PiiEngine, SanitizeResult
from policy.schema import Policy
from policy.store import PolicyStore
from providers.fallback_chain import AllProvidersDownError, FallbackChain, FallbackResult
from router.heuristic import classify_difficulty
from router.normalizer import RequestNormalizer


class ProviderFailureError(Exception):
    def __init__(self, tier: str, session_id: str, audit_record: AuditRecord) -> None:
        super().__init__(f"all providers down for tier {tier!r}")
        self.tier = tier
        self.session_id = session_id
        self.audit_record = audit_record


@dataclass
class ChatResult:
    request_id: str
    session_id: str
    content: str
    model_id: str
    provider: str
    difficulty: Optional[str]
    usage: dict
    cost_usd: Optional[float]
    unresolved_tokens: list
    review_required: bool
    policy_id: str
    policy_version: str
    sanitized_prompt: str = ""
    raw_model_output: str = ""
    audit_record: Any = None


@dataclass
class Prepared:
    """Output of normalize -> sanitize -> route, shared by both the
    non-streaming and streaming paths."""
    request_id: str
    session_id: str
    policy: Policy
    virtual_key_id: Optional[str]
    team_id: Optional[str]
    sanitize_result: SanitizeResult
    sanitized_prompt: str
    difficulty: str
    fb_result: FallbackResult
    t_start: float
    pii_sanitize_ms: float
    router_ms: float


class Orchestrator:
    def __init__(
        self,
        pii: PiiEngine,
        policy_store: PolicyStore,
        fallback_chain: FallbackChain,
        audit_chain: AuditChain,
        detector_versions: dict[str, str],
        pack_versions: dict[str, str],
    ) -> None:
        self._pii = pii
        self._policy_store = policy_store
        self._fallback_chain = fallback_chain
        self._audit_chain = audit_chain
        self._normalizer = RequestNormalizer()
        self._detector_versions = detector_versions
        self._pack_versions = pack_versions

    async def prepare_dispatch(
        self,
        raw_payload: dict[str, Any],
        policy_id: str = "default",
        virtual_key_id: Optional[str] = None,
        team_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Prepared:
        request_id = str(uuid.uuid4())
        t_start = time.monotonic()
        session_id = session_id or raw_payload.get("session_id") or request_id

        ctx = self._normalizer.normalize(raw_payload)
        policy = self._policy_store.get(policy_id)

        t0 = time.monotonic()
        try:
            sanitize_result = self._pii.sanitize_messages(ctx.messages, session_id, policy)
        except BlockedContentError as err:
            pii_sanitize_ms = (time.monotonic() - t0) * 1000.0
            record = AuditRecord(
                ts=time.time(), request_id=request_id, session_id=session_id,
                virtual_key_id=virtual_key_id, team_id=team_id, event="blocked",
                policy_id=policy.policy_id, policy_version=policy.version,
                detector_versions=self._detector_versions, pack_versions=self._pack_versions,
                span_counts_by_label=err.span_counts_by_label, blocked_labels=err.labels,
                pii_sanitize_ms=round(pii_sanitize_ms, 3), total_ms=round((time.monotonic() - t_start) * 1000.0, 3),
            )
            self._audit_chain.append(record)
            err.audit_record = record
            raise
        pii_sanitize_ms = (time.monotonic() - t0) * 1000.0

        sanitized_ctx = ctx.model_copy(update={"messages": sanitize_result.messages})
        sanitized_prompt = "\n".join(m.content for m in sanitize_result.messages if isinstance(m.content, str))
        difficulty = classify_difficulty(self._pii.strip_tokens_for_classification(sanitized_prompt))

        t1 = time.monotonic()
        try:
            fb_result = await self._fallback_chain.dispatch(request_id, difficulty, sanitized_ctx)
        except AllProvidersDownError as err:
            router_ms = (time.monotonic() - t1) * 1000.0
            record = AuditRecord(
                ts=time.time(), request_id=request_id, session_id=session_id,
                virtual_key_id=virtual_key_id, team_id=team_id, event="provider_failure",
                policy_id=policy.policy_id, policy_version=policy.version,
                detector_versions=self._detector_versions, pack_versions=self._pack_versions,
                span_counts_by_label=sanitize_result.span_counts_by_label,
                redacted_count=sanitize_result.redacted_count, difficulty=difficulty,
                pii_sanitize_ms=round(pii_sanitize_ms, 3), router_ms=round(router_ms, 3),
                total_ms=round((time.monotonic() - t_start) * 1000.0, 3),
            )
            self._audit_chain.append(record)
            raise ProviderFailureError(err.tier, session_id, record) from err
        router_ms = (time.monotonic() - t1) * 1000.0

        return Prepared(
            request_id=request_id, session_id=session_id, policy=policy,
            virtual_key_id=virtual_key_id, team_id=team_id,
            sanitize_result=sanitize_result, sanitized_prompt=sanitized_prompt,
            difficulty=difficulty, fb_result=fb_result, t_start=t_start,
            pii_sanitize_ms=pii_sanitize_ms, router_ms=router_ms,
        )

    async def chat(
        self,
        raw_payload: dict[str, Any],
        policy_id: str = "default",
        virtual_key_id: Optional[str] = None,
        team_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> ChatResult:
        p = await self.prepare_dispatch(raw_payload, policy_id, virtual_key_id, team_id, session_id)

        t2 = time.monotonic()
        output_text, output_token_ids = self._pii.scan_output(
            p.fb_result.response.content, p.session_id, p.policy
        )
        output_scan_ms = (time.monotonic() - t2) * 1000.0

        t3 = time.monotonic()
        final_text, unresolved, review_required = self._pii.rehydrate(
            output_text, p.session_id, p.sanitize_result.token_ids, output_token_ids
        )
        pii_rehydrate_ms = (time.monotonic() - t3) * 1000.0

        return self._finalize(p, final_text, unresolved, review_required, output_scan_ms, pii_rehydrate_ms)

    def finalize_stream(
        self,
        prepared: Prepared,
        final_text: str,
        unresolved: list,
        review_required: bool,
        output_scan_ms: float,
        pii_rehydrate_ms: float,
        ttfb_ms: Optional[float] = None,
    ) -> ChatResult:
        return self._finalize(
            prepared, final_text, unresolved, review_required, output_scan_ms, pii_rehydrate_ms,
            stream=True, ttfb_ms=ttfb_ms,
        )

    def _finalize(
        self,
        p: Prepared,
        final_text: str,
        unresolved: list,
        review_required: bool,
        output_scan_ms: float,
        pii_rehydrate_ms: float,
        stream: bool = False,
        ttfb_ms: Optional[float] = None,
    ) -> ChatResult:
        total_ms = (time.monotonic() - p.t_start) * 1000.0
        provider = p.fb_result.route.provider
        cost_usd = provider.pop_cost(p.request_id) if hasattr(provider, "pop_cost") else None

        record = AuditRecord(
            ts=time.time(), request_id=p.request_id, session_id=p.session_id,
            virtual_key_id=p.virtual_key_id, team_id=p.team_id, event="completed",
            policy_id=p.policy.policy_id, policy_version=p.policy.version,
            detector_versions=self._detector_versions, pack_versions=self._pack_versions,
            span_counts_by_label=p.sanitize_result.span_counts_by_label,
            redacted_count=p.sanitize_result.redacted_count, difficulty=p.difficulty,
            model_id=p.fb_result.response.model_id, provider=p.fb_result.response.provider,
            fallback_chain_position=p.fb_result.fallback_chain_position, circuit_state=p.fb_result.circuit_state,
            unresolved_tokens=unresolved, review_required=review_required,
            pii_sanitize_ms=round(p.pii_sanitize_ms, 3), router_ms=round(p.router_ms, 3),
            pii_rehydrate_ms=round(pii_rehydrate_ms, 3), output_scan_ms=round(output_scan_ms, 3),
            total_ms=round(total_ms, 3), usage=p.fb_result.response.usage, cost_usd=cost_usd,
            stream=stream, ttfb_ms=ttfb_ms,
        )
        self._audit_chain.append(record)

        return ChatResult(
            request_id=p.request_id, session_id=p.session_id, content=final_text,
            model_id=p.fb_result.response.model_id, provider=p.fb_result.response.provider,
            difficulty=p.difficulty, usage=p.fb_result.response.usage, cost_usd=cost_usd,
            unresolved_tokens=unresolved, review_required=review_required,
            policy_id=p.policy.policy_id, policy_version=p.policy.version,
            sanitized_prompt=p.sanitized_prompt, raw_model_output=p.fb_result.response.content,
            audit_record=record,
        )
