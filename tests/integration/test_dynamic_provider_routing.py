"""Verifies the dynamic per-model resolver seam in orchestrator.py: an
explicit registered `model` bypasses the difficulty-tier FallbackChain
entirely, while `model: "auto"`/absent/unregistered falls through to the
existing heuristic-difficulty behavior unchanged.
"""
from __future__ import annotations

import json

import pytest
from audit.chain import AuditChain
from audit.sinks import JsonlSink
from detect.pipeline import DetectionPipeline
from orchestrator import Orchestrator, ProviderFailureError
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
    def __init__(self) -> None:
        self.seen_model_ids: list[str] = []

    async def complete(self, request_id: str, model_id: str, ctx: RequestContext) -> ProviderResponse:
        self.seen_model_ids.append(model_id)
        return ProviderResponse(
            request_id=request_id, model_id=model_id, provider="dynamic-provider", content="hi there",
            usage={"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}, latency_ms=1.0,
        )


class _AlwaysFailProvider(ProviderAdapter):
    async def complete(self, request_id: str, model_id: str, ctx: RequestContext) -> ProviderResponse:
        raise RuntimeError("upstream unreachable")


class _FakeDynamicRouter:
    """Duck-typed stand-in for providers.dynamic_router.DynamicProviderRouter --
    only the seam's `resolve_route(model_id) -> Route | None` contract matters
    here, not the real registry/adapter-caching machinery (covered by
    tests/unit/test_dynamic_router.py and tests/unit/test_registry_store.py)."""

    def __init__(self, routes: dict[str, Route]) -> None:
        self._routes = routes

    def resolve_route(self, model_id: str | None) -> Route | None:
        if not model_id:
            return None
        return self._routes.get(model_id)


def _build_orchestrator(tmp_path, provider, dynamic_router=None) -> tuple[Orchestrator, str]:
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

    orch = Orchestrator(
        pii, policy_store, fallback_chain, audit_chain, DETECTOR_VERSIONS, PACK_VERSIONS,
        dynamic_router=dynamic_router,
    )
    return orch, audit_path


def _read_jsonl(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


async def test_registered_model_bypasses_difficulty_router(tmp_path):
    tier_provider = EchoingStubProvider()
    dynamic_provider = EchoingStubProvider()
    dynamic_router = _FakeDynamicRouter({
        "demo-model": Route(provider=dynamic_provider, model_id="llama-3.1-8b-instant", provider_name="groq"),
    })
    orch, audit_path = _build_orchestrator(tmp_path, tier_provider, dynamic_router)

    result = await orch.chat({"model": "demo-model", "messages": [{"role": "user", "content": "hi"}]})

    assert result.difficulty == "dynamic"
    assert result.provider == "groq"
    assert result.model_id == "llama-3.1-8b-instant"
    assert dynamic_provider.seen_model_ids == ["llama-3.1-8b-instant"]
    assert tier_provider.seen_model_ids == []  # difficulty-tier chain never touched

    lines = _read_jsonl(audit_path)
    assert lines[0]["difficulty"] == "dynamic"


async def test_auto_model_falls_through_to_difficulty_router(tmp_path):
    tier_provider = EchoingStubProvider()
    dynamic_router = _FakeDynamicRouter({})  # nothing registered
    orch, _ = _build_orchestrator(tmp_path, tier_provider, dynamic_router)

    result = await orch.chat({"model": "auto", "messages": [{"role": "user", "content": "hi there"}]})

    assert result.difficulty == "simple"
    assert tier_provider.seen_model_ids == ["simple"]


async def test_no_model_field_falls_through_to_difficulty_router(tmp_path):
    tier_provider = EchoingStubProvider()
    orch, _ = _build_orchestrator(tmp_path, tier_provider, dynamic_router=None)

    result = await orch.chat({"messages": [{"role": "user", "content": "hi there"}]})

    assert result.difficulty == "simple"


async def test_unregistered_model_falls_through_to_difficulty_router(tmp_path):
    tier_provider = EchoingStubProvider()
    dynamic_router = _FakeDynamicRouter({})
    orch, _ = _build_orchestrator(tmp_path, tier_provider, dynamic_router)

    result = await orch.chat({"model": "not-registered", "messages": [{"role": "user", "content": "hi there"}]})

    assert result.difficulty == "simple"


async def test_dynamic_route_failure_raises_provider_failure_error_and_audits(tmp_path):
    tier_provider = EchoingStubProvider()
    dynamic_router = _FakeDynamicRouter({
        "demo-model": Route(provider=_AlwaysFailProvider(), model_id="llama-3.1-8b-instant", provider_name="groq"),
    })
    orch, audit_path = _build_orchestrator(tmp_path, tier_provider, dynamic_router)

    with pytest.raises(ProviderFailureError):
        await orch.chat({"model": "demo-model", "messages": [{"role": "user", "content": "hi"}]})

    lines = _read_jsonl(audit_path)
    assert lines[0]["event"] == "provider_failure"
    assert lines[0]["difficulty"] == "dynamic"
