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
from typing import Any

from audit.chain import AuditChain
from contracts.audit import AuditRecord
from obs.metrics import REQUEST_DURATION_SECONDS
from obs.otel import record_latency, record_pii_density, record_rehydration_overhead, record_tokens
from obs.tracing import stage_span
from pii import BlockedContentError, PiiEngine, SanitizeResult
from policy.schema import Policy
from policy.store import PolicyStore
from providers.dynamic_router import DynamicProviderRouter
from providers.fallback_chain import AllProvidersDownError, FallbackChain, FallbackResult
from router.embedding_classifier import EmbeddingRouterClassifier, classify_difficulty_cascade
from router.embedding_router import EmbeddingRouter, RouterDecision
from router.heuristic import classify_difficulty
from router.normalizer import RequestNormalizer

# G7: only let the size-gated embedding router override the
# heuristic/G6-classifier cascade's result when it's reasonably
# confident -- otherwise fail open to the earlier stage rather than
# trusting a near-coin-flip decision, especially likely on the
# anchor_similarity tier with very little labeled data.
_ROUTER_MIN_CONFIDENCE = 0.4


def _last_user_text(messages: list) -> str:
    """The newest user turn's text. A chat request carries the whole
    conversation history for context, but the per-user transaction view
    should show only what the user actually said *this* turn -- not the
    entire running transcript re-dumped on every request."""
    for m in reversed(messages):
        if getattr(m, "role", None) == "user" and isinstance(getattr(m, "content", None), str):
            return m.content
    for m in reversed(messages):
        if isinstance(getattr(m, "content", None), str):
            return m.content
    return ""


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
    difficulty: str | None
    usage: dict
    cost_usd: float | None
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
    virtual_key_id: str | None
    team_id: str | None
    sanitize_result: SanitizeResult
    sanitized_prompt: str
    original_prompt: str
    redacted_prompt: str
    difficulty: str
    router_decision: RouterDecision
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
        embedding_classifier: EmbeddingRouterClassifier | None = None,
        embedding_router: EmbeddingRouter | None = None,
        dynamic_router: DynamicProviderRouter | None = None,
        transaction_store: Any = None,
    ) -> None:
        self._pii = pii
        self._policy_store = policy_store
        self._fallback_chain = fallback_chain
        self._audit_chain = audit_chain
        self._normalizer = RequestNormalizer()
        self._detector_versions = detector_versions
        self._pack_versions = pack_versions
        self._embedding_classifier = embedding_classifier or EmbeddingRouterClassifier.load()
        self._embedding_router = embedding_router or EmbeddingRouter.load()
        self._dynamic_router = dynamic_router
        # Optional per-request prompt/reply store (gateway/auth/transaction_store.py)
        # backing the admin Users-tab drill-down. None in tests / when unset.
        self._transaction_store = transaction_store

    def _route_failure_record(
        self,
        request_id: str,
        session_id: str,
        virtual_key_id: str | None,
        team_id: str | None,
        policy: Policy,
        sanitize_result: SanitizeResult,
        difficulty: str,
        router_decision: RouterDecision,
        pii_sanitize_ms: float,
        router_ms: float,
        t_start: float,
    ) -> AuditRecord:
        return AuditRecord(
            ts=time.time(), request_id=request_id, session_id=session_id,
            virtual_key_id=virtual_key_id, team_id=team_id, event="provider_failure",
            policy_id=policy.policy_id, policy_version=policy.version,
            detector_versions=self._detector_versions, pack_versions=self._pack_versions,
            span_counts_by_label=sanitize_result.span_counts_by_label,
            redacted_count=sanitize_result.redacted_count, difficulty=difficulty,
            router_tier=router_decision.tier, router_confidence=router_decision.confidence,
            router_rationale=router_decision.rationale,
            pii_sanitize_ms=round(pii_sanitize_ms, 3), router_ms=round(router_ms, 3),
            total_ms=round((time.monotonic() - t_start) * 1000.0, 3),
        )

    def _record_transaction(
        self,
        *,
        request_id: str,
        session_id: str | None,
        team_id: str | None,
        virtual_key_id: str | None,
        model: str | None,
        status: str,
        redaction_rules: list[str],
        input_tokens: int,
        output_tokens: int,
        cost: float | None,
        original_prompt: str,
        redacted_prompt: str,
        llm_reply: str,
        rehydrated_reply: str,
    ) -> None:
        """Best-effort write to the per-user prompt/reply store. Never lets a
        store failure break the response path -- the transaction view is an
        admin convenience, not part of request correctness."""
        if self._transaction_store is None:
            return
        try:
            self._transaction_store.record(
                request_id=request_id, session_id=session_id, team_id=team_id, virtual_key_id=virtual_key_id,
                model=model, status=status, redaction_rules=redaction_rules,
                input_tokens=input_tokens, output_tokens=output_tokens, cost=cost,
                original_prompt=original_prompt, redacted_prompt=redacted_prompt,
                llm_reply=llm_reply, rehydrated_reply=rehydrated_reply,
            )
        except Exception:  # noqa: BLE001 -- deliberately swallow; see docstring
            pass

    async def prepare_dispatch(
        self,
        raw_payload: dict[str, Any],
        policy_id: str = "default",
        virtual_key_id: str | None = None,
        team_id: str | None = None,
        session_id: str | None = None,
    ) -> Prepared:
        request_id = str(uuid.uuid4())
        t_start = time.monotonic()
        session_id = session_id or raw_payload.get("session_id") or request_id

        ctx = self._normalizer.normalize(raw_payload)
        policy = self._policy_store.get(policy_id)
        original_prompt = _last_user_text(ctx.messages)

        t0 = time.monotonic()
        try:
            with stage_span("sanitize", request_id=request_id, session_id=session_id, policy_id=policy.policy_id):
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
            # A blocked request never reaches a model, but the admin drill-down
            # still shows it (status=blocked, no reply) so the operator can see
            # what was rejected and why.
            self._record_transaction(
                request_id=request_id, session_id=session_id, team_id=team_id, virtual_key_id=virtual_key_id,
                model=ctx.model_hint, status="blocked", redaction_rules=err.labels,
                input_tokens=0, output_tokens=0, cost=None,
                original_prompt=original_prompt, redacted_prompt="", llm_reply="", rehydrated_reply="",
            )
            raise
        pii_sanitize_ms = (time.monotonic() - t0) * 1000.0
        REQUEST_DURATION_SECONDS.labels(stage="sanitize").observe(pii_sanitize_ms / 1000.0)
        record_latency("sanitize", pii_sanitize_ms)

        sanitized_ctx = ctx.model_copy(update={"messages": sanitize_result.messages})
        sanitized_prompt = "\n".join(m.content for m in sanitize_result.messages if isinstance(m.content, str))
        redacted_prompt = _last_user_text(sanitize_result.messages)

        t1 = time.monotonic()
        dynamic_route = self._dynamic_router.resolve_route(ctx.model_hint) if self._dynamic_router else None

        if dynamic_route is not None:
            difficulty = "dynamic"
            router_decision = RouterDecision(
                difficulty="dynamic", confidence=1.0, tier="explicit_model",
                rationale=f"model {ctx.model_hint!r} resolved via provider registry (provider={dynamic_route.provider_name})",
            )
            try:
                with stage_span("route", request_id=request_id, difficulty=difficulty):
                    response = await dynamic_route.provider.complete(request_id, dynamic_route.model_id, sanitized_ctx)
                fb_result = FallbackResult(
                    response=response.model_copy(update={"provider": dynamic_route.provider_name}),
                    fallback_chain_position=0, circuit_state="n/a", route=dynamic_route,
                )
            except Exception as exc:
                router_ms = (time.monotonic() - t1) * 1000.0
                record = self._route_failure_record(
                    request_id, session_id, virtual_key_id, team_id, policy, sanitize_result,
                    difficulty, router_decision, pii_sanitize_ms, router_ms, t_start,
                )
                self._audit_chain.append(record)
                raise ProviderFailureError(f"model:{ctx.model_hint}", session_id, record) from exc
        else:
            classification_text = self._pii.strip_tokens_for_classification(sanitized_prompt)
            heuristic_difficulty = classify_difficulty(classification_text)
            difficulty = classify_difficulty_cascade(classification_text, heuristic_difficulty, self._embedding_classifier)
            router_decision = self._embedding_router.classify(classification_text)
            if router_decision.confidence >= _ROUTER_MIN_CONFIDENCE:
                difficulty = router_decision.difficulty

            try:
                with stage_span("route", request_id=request_id, difficulty=difficulty):
                    fb_result = await self._fallback_chain.dispatch(request_id, difficulty, sanitized_ctx)
            except AllProvidersDownError as err:
                router_ms = (time.monotonic() - t1) * 1000.0
                record = self._route_failure_record(
                    request_id, session_id, virtual_key_id, team_id, policy, sanitize_result,
                    difficulty, router_decision, pii_sanitize_ms, router_ms, t_start,
                )
                self._audit_chain.append(record)
                raise ProviderFailureError(err.tier, session_id, record) from err

        router_ms = (time.monotonic() - t1) * 1000.0
        REQUEST_DURATION_SECONDS.labels(stage="route").observe(router_ms / 1000.0)
        record_latency("route", router_ms)

        return Prepared(
            request_id=request_id, session_id=session_id, policy=policy,
            virtual_key_id=virtual_key_id, team_id=team_id,
            sanitize_result=sanitize_result, sanitized_prompt=sanitized_prompt,
            original_prompt=original_prompt, redacted_prompt=redacted_prompt,
            difficulty=difficulty, router_decision=router_decision, fb_result=fb_result, t_start=t_start,
            pii_sanitize_ms=pii_sanitize_ms, router_ms=router_ms,
        )

    async def chat(
        self,
        raw_payload: dict[str, Any],
        policy_id: str = "default",
        virtual_key_id: str | None = None,
        team_id: str | None = None,
        session_id: str | None = None,
    ) -> ChatResult:
        p = await self.prepare_dispatch(raw_payload, policy_id, virtual_key_id, team_id, session_id)

        t2 = time.monotonic()
        if p.policy.output_scan.enabled:
            with stage_span("output_scan", request_id=p.request_id, session_id=p.session_id):
                output_text, output_token_ids = self._pii.scan_output(
                    p.fb_result.response.content, p.session_id, p.policy
                )
        else:
            # Output scanning disabled: the model's response is returned as-is
            # (no new output-side redaction). Input-side tokens are still
            # rehydrated below so the user's own PII placeholders resolve back.
            output_text, output_token_ids = p.fb_result.response.content, set()
        output_scan_ms = (time.monotonic() - t2) * 1000.0
        REQUEST_DURATION_SECONDS.labels(stage="output_scan").observe(output_scan_ms / 1000.0)
        record_latency("output_scan", output_scan_ms)

        t3 = time.monotonic()
        with stage_span("rehydrate", request_id=p.request_id, session_id=p.session_id):
            final_text, unresolved, review_required = self._pii.rehydrate(
                output_text, p.session_id, p.sanitize_result.token_ids, output_token_ids
            )
        pii_rehydrate_ms = (time.monotonic() - t3) * 1000.0
        REQUEST_DURATION_SECONDS.labels(stage="rehydrate").observe(pii_rehydrate_ms / 1000.0)
        record_latency("rehydrate", pii_rehydrate_ms)
        record_rehydration_overhead(pii_rehydrate_ms)

        return self._finalize(p, final_text, unresolved, review_required, output_scan_ms, pii_rehydrate_ms)

    def finalize_stream(
        self,
        prepared: Prepared,
        final_text: str,
        unresolved: list,
        review_required: bool,
        output_scan_ms: float,
        pii_rehydrate_ms: float,
        ttfb_ms: float | None = None,
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
        ttfb_ms: float | None = None,
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
            router_tier=p.router_decision.tier, router_confidence=p.router_decision.confidence,
            router_rationale=p.router_decision.rationale,
            model_id=p.fb_result.response.model_id, provider=p.fb_result.response.provider,
            fallback_chain_position=p.fb_result.fallback_chain_position, circuit_state=p.fb_result.circuit_state,
            unresolved_tokens=unresolved, review_required=review_required,
            pii_sanitize_ms=round(p.pii_sanitize_ms, 3), router_ms=round(p.router_ms, 3),
            pii_rehydrate_ms=round(pii_rehydrate_ms, 3), output_scan_ms=round(output_scan_ms, 3),
            total_ms=round(total_ms, 3), usage=p.fb_result.response.usage, cost_usd=cost_usd,
            stream=stream, ttfb_ms=ttfb_ms,
        )
        with stage_span("audit", request_id=p.request_id, session_id=p.session_id):
            self._audit_chain.append(record)
        REQUEST_DURATION_SECONDS.labels(stage="total").observe(total_ms / 1000.0)
        record_latency("total", total_ms)

        usage_for_tx = p.fb_result.response.usage or {}
        self._record_transaction(
            request_id=p.request_id, session_id=p.session_id, team_id=p.team_id, virtual_key_id=p.virtual_key_id,
            model=p.fb_result.response.model_id,
            status="redacted" if p.sanitize_result.redacted_count > 0 else "clean",
            redaction_rules=sorted(p.sanitize_result.span_counts_by_label.keys()),
            input_tokens=usage_for_tx.get("prompt_tokens", 0),
            output_tokens=usage_for_tx.get("completion_tokens", 0),
            cost=cost_usd,
            original_prompt=p.original_prompt, redacted_prompt=p.redacted_prompt,
            llm_reply=p.fb_result.response.content, rehydrated_reply=final_text,
        )

        usage = p.fb_result.response.usage or {}
        record_tokens(usage.get("prompt_tokens", 0), "prompt")
        record_tokens(usage.get("completion_tokens", 0), "completion")
        total_spans = sum(p.sanitize_result.span_counts_by_label.values())
        if p.sanitized_prompt:
            record_pii_density((total_spans / len(p.sanitized_prompt)) * 1000.0)

        return ChatResult(
            request_id=p.request_id, session_id=p.session_id, content=final_text,
            model_id=p.fb_result.response.model_id, provider=p.fb_result.response.provider,
            difficulty=p.difficulty, usage=p.fb_result.response.usage, cost_usd=cost_usd,
            unresolved_tokens=unresolved, review_required=review_required,
            policy_id=p.policy.policy_id, policy_version=p.policy.version,
            sanitized_prompt=p.sanitized_prompt, raw_model_output=p.fb_result.response.content,
            audit_record=record,
        )
