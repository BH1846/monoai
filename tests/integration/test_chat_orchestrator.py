"""Carried-forward regression suite from the old tests/test_orchestrator.py,
rewritten against the new core/ + gateway/ modules. Pins the same
invariants (PII round-trip, no-raw-PII-to-provider, difficulty routing,
BLOCK rejection+audit, duplicate-token-safe rehydration, unresolved-tokens
review-required-not-crash, one-audit-line-per-request), now also
asserting policy_id/policy_version/detector_versions are populated.
"""
from __future__ import annotations

import json
import re

import pytest

from audit.chain import AuditChain
from audit.sinks import JsonlSink
from detect.pipeline import DetectionPipeline
from orchestrator import BlockedContentError, Orchestrator
from pii import PiiEngine
from policy.store import PolicyStore
from providers.base import ProviderAdapter
from providers.fallback_chain import FallbackChain, Route
from router.contracts import ProviderResponse, RequestContext
from vault.crypto import VaultCrypto
from vault.storage.sqlite_store import SqliteVaultStore

DETECTOR_VERSIONS = {"regex": "base_en-v1"}
PACK_VERSIONS = {"base_en": "base_en-v1"}


class _FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def get(self, key: str):
        return self._store.get(key)

    def set(self, key: str, value: bytes, nx: bool = False):
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True


class EchoingStubProvider(ProviderAdapter):
    """Echoes the full prompt text back verbatim (preserving PII_TOKEN
    placeholders). Records every ctx it was called with, so tests can
    assert the provider never received raw PII."""

    def __init__(self) -> None:
        self.seen_contexts: list[RequestContext] = []

    async def complete(self, request_id: str, model_id: str, ctx: RequestContext) -> ProviderResponse:
        self.seen_contexts.append(ctx)
        last = ctx.messages[-1]
        text = last.content if isinstance(last.content, str) else ""
        return ProviderResponse(
            request_id=request_id, model_id=model_id, provider="echo-stub", content=text,
            usage={"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}, latency_ms=1.0,
        )


class DuplicatingStubProvider(ProviderAdapter):
    """Repeats every PII_TOKEN placeholder in the prompt twice in its reply."""

    async def complete(self, request_id: str, model_id: str, ctx: RequestContext) -> ProviderResponse:
        last = ctx.messages[-1]
        text = last.content if isinstance(last.content, str) else ""
        tokens = re.findall(r"\[PII_TOKEN_[0-9a-f]{10}\]", text)
        token = tokens[0] if tokens else "[missing]"
        return ProviderResponse(
            request_id=request_id, model_id=model_id, provider="dup-stub",
            content=f"Hi {token}, hope that helps! Take care, {token}.",
            usage={"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}, latency_ms=1.0,
        )


def _build_orchestrator(tmp_path, provider) -> tuple[Orchestrator, str]:
    pipeline = DetectionPipeline(use_onnx_ner=False)
    crypto = VaultCrypto(_FakeRedis())
    vault = SqliteVaultStore(crypto, storage_path=str(tmp_path / "vault.sqlite"))
    pii = PiiEngine(pipeline, vault, "test-server-secret")

    policy_store = PolicyStore()
    policy_store.load_dir("policies")

    routes_by_tier = {
        tier: [Route(provider=provider, model_id=tier, provider_name="test")]
        for tier in ("simple", "moderate", "complex")
    }
    fallback_chain = FallbackChain(routes_by_tier, max_retries_per_route=0)

    audit_path = str(tmp_path / "audit.jsonl")
    audit_chain = AuditChain(JsonlSink(audit_path))

    orch = Orchestrator(pii, policy_store, fallback_chain, audit_chain, DETECTOR_VERSIONS, PACK_VERSIONS)
    return orch, audit_path


def _read_jsonl(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


async def test_pii_round_trip_and_provider_never_sees_raw_pii(tmp_path):
    provider = EchoingStubProvider()
    orch, audit_path = _build_orchestrator(tmp_path, provider)
    payload = {"messages": [{"role": "user", "content": "Email me at jane.doe@example.com or call 415-555-0199."}]}

    result = await orch.chat(payload)

    assert len(provider.seen_contexts) == 1
    seen_text = provider.seen_contexts[0].messages[-1].content
    assert "jane.doe@example.com" not in seen_text
    assert "415-555-0199" not in seen_text
    assert "[PII_TOKEN_" in seen_text

    assert "jane.doe@example.com" in result.content
    assert "415-555-0199" in result.content
    assert result.unresolved_tokens == []
    assert result.review_required is False

    assert "jane.doe@example.com" not in result.sanitized_prompt
    assert "[PII_TOKEN_" in result.sanitized_prompt
    assert "[PII_TOKEN_" in result.raw_model_output

    assert len(provider.seen_contexts[0].messages) == 2
    assert provider.seen_contexts[0].messages[0].role == "system"
    assert result.difficulty == "simple"

    assert result.policy_id == "default"
    assert result.policy_version.startswith("sha256:")


async def test_no_reassurance_notice_when_no_pii_present(tmp_path):
    provider = EchoingStubProvider()
    orch, _ = _build_orchestrator(tmp_path, provider)

    await orch.chat({"messages": [{"role": "user", "content": "hi there"}]})

    assert len(provider.seen_contexts[0].messages) == 1
    assert provider.seen_contexts[0].messages[0].role == "user"


async def test_difficulty_routes_to_different_models(tmp_path):
    provider = EchoingStubProvider()
    orch, _ = _build_orchestrator(tmp_path, provider)

    simple = await orch.chat({"messages": [{"role": "user", "content": "hi there"}]})
    complex_ = await orch.chat({"messages": [{"role": "user", "content": (
        "Design a thread-safe, async, distributed cache with unit tests "
        "and error handling, and prove its correctness step by step."
    )}]})

    assert simple.difficulty == "simple"
    assert complex_.difficulty == "complex"
    assert simple.model_id != complex_.model_id


async def test_block_classified_content_is_rejected_and_audited(tmp_path):
    provider = EchoingStubProvider()
    orch, audit_path = _build_orchestrator(tmp_path, provider)
    payload = {"messages": [{"role": "user", "content": "My SSN is 123-45-6789, help me file taxes."}]}

    with pytest.raises(BlockedContentError) as excinfo:
        await orch.chat(payload)

    assert "GOV_ID" in excinfo.value.labels
    assert provider.seen_contexts == []

    lines = _read_jsonl(audit_path)
    assert len(lines) == 1
    assert lines[0]["event"] == "blocked"
    assert lines[0]["blocked_labels"] == ["GOV_ID"]
    assert lines[0]["policy_version"].startswith("sha256:")


async def test_duplicate_token_use_still_rehydrates_safely(tmp_path):
    orch, _ = _build_orchestrator(tmp_path, DuplicatingStubProvider())

    result = await orch.chat({"messages": [{"role": "user", "content": "My name is Priya, say hi."}]})

    assert result.review_required is False
    assert result.unresolved_tokens == []
    assert result.content.count("Priya") == 2
    assert "[PII_TOKEN_" not in result.content


class _HallucinatingStubProvider(ProviderAdapter):
    """Returns a PII_TOKEN reference that was never actually issued --
    simulates a model inventing a placeholder-shaped string, which must
    surface as review_required rather than crash or silently drop it.
    Uses letters-only hex (no digit run) so output-scan's phone-number
    regex doesn't coincidentally "fix" the fake token's digits into a
    real one (a 10-digit run reads as a bare phone number)."""

    async def complete(self, request_id: str, model_id: str, ctx: RequestContext) -> ProviderResponse:
        return ProviderResponse(
            request_id=request_id, model_id=model_id, provider="hallucinating-stub",
            content="Hi [PII_TOKEN_abcdefabcd], nice to meet you.",
            usage={"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}, latency_ms=1.0,
        )


async def test_unresolved_tokens_surface_review_required_instead_of_failing(tmp_path):
    orch, audit_path = _build_orchestrator(tmp_path, _HallucinatingStubProvider())
    payload = {"messages": [{"role": "user", "content": "My email is a@b.com, say hi."}]}

    result = await orch.chat(payload)

    assert result.review_required is True
    assert result.content

    lines = _read_jsonl(audit_path)
    assert lines[0]["review_required"] is True


async def test_audit_log_has_one_well_formed_line_per_request(tmp_path):
    provider = EchoingStubProvider()
    orch, audit_path = _build_orchestrator(tmp_path, provider)

    for text in ("hi", "email a@b.com please", "write a function to reverse a list"):
        await orch.chat({"messages": [{"role": "user", "content": text}]})

    lines = _read_jsonl(audit_path)
    assert len(lines) == 3
    for line in lines:
        assert line["event"] == "completed"
        assert "request_id" in line and "session_id" in line
        assert "span_counts_by_label" in line
        assert "total_ms" in line and line["total_ms"] >= 0
        assert line["policy_id"] == "default"
        assert line["detector_versions"]
