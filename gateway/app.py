"""FastAPI surface: POST /v1/chat/completions, /health/live, /health/ready,
GET /v1/evidence/export, /v1/admin/* (key-store CRUD + policy reload).
Extends monoai_gateway/app.py's lifespan-wiring pattern with auth,
streaming, the new core/ modules, and per-tier provider fallback chains.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI

from audit.chain import AuditChain
from audit.sinks import JsonlSink, read_last_hash
from auth.middleware import register_auth_exception_handlers
from auth.rate_limit import TokenBucketRateLimiter
from auth.store import SqliteKeyStore
from config import Settings, load_settings
from detect.pipeline import DetectionPipeline
from orchestrator import Orchestrator
from pii import PiiEngine
from policy.store import PolicyStore
from providers.base import ProviderAdapter
from providers.fallback_chain import FallbackChain, Route
from providers.ollama import OllamaProvider
from providers.openai_compatible import CloudRoute, OpenAICompatibleProvider
from providers.stub import StubProvider
from vault.crypto import VaultCrypto
from vault.storage.sqlite_store import SqliteVaultStore

DETECTOR_VERSIONS = {"regex": "base_en-v1", "secrets": "base_en-v1", "ner": "base_en-v1", "locked_span": "base_en-v1"}
PACK_VERSIONS = {"base_en": "base_en-v1"}


def _build_provider(settings: Settings) -> ProviderAdapter:
    if settings.provider == "ollama":
        return OllamaProvider(base_url=settings.ollama_base_url)
    if settings.provider == "stub":
        return StubProvider()
    if settings.provider == "cloud":
        if not settings.cloud_api_base_url:
            raise ValueError("MONOAI_PROVIDER=cloud requires CLOUD_API_BASE_URL (see .env at the repo root)")

        tiers = {
            "simple": (settings.cloud_model_simple, settings.cloud_api_key_simple or settings.cloud_api_key),
            "moderate": (settings.cloud_model_moderate, settings.cloud_api_key_moderate or settings.cloud_api_key),
            "complex": (settings.cloud_model_complex, settings.cloud_api_key_complex or settings.cloud_api_key),
        }
        missing = [tier for tier, (model, key) in tiers.items() if not model or not key]
        if missing:
            raise ValueError(
                f"MONOAI_PROVIDER=cloud is missing model/key config for tier(s): {', '.join(missing)} "
                "(see .env at the repo root)"
            )
        routes = {tier: CloudRoute(model=model, api_key=key) for tier, (model, key) in tiers.items()}
        return OpenAICompatibleProvider(base_url=settings.cloud_api_base_url, routes=routes, provider_name=settings.cloud_provider_name)
    raise ValueError(f"unknown MONOAI_PROVIDER: {settings.provider!r} (expected 'stub', 'ollama', or 'cloud')")


def _build_fallback_chain(settings: Settings, provider: ProviderAdapter) -> FallbackChain:
    routes_by_tier = {
        tier: [Route(provider=provider, model_id=tier, provider_name=settings.provider)]
        for tier in ("simple", "moderate", "complex")
    }
    return FallbackChain(
        routes_by_tier,
        failure_threshold=settings.circuit_failure_threshold,
        open_duration_s=settings.circuit_open_duration_s,
        max_retries_per_route=settings.max_retries_per_route,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()

    valkey_client = redis.Redis(host=settings.valkey_host, port=settings.valkey_port, password=settings.valkey_password)

    pipeline = DetectionPipeline(use_onnx_ner=settings.pii_use_onnx_ner)
    vault_crypto = VaultCrypto(valkey_client, key_name=settings.valkey_key_name)
    vault_store = SqliteVaultStore(vault_crypto, storage_path=settings.vault_storage_path)
    pii = PiiEngine(pipeline, vault_store, settings.session_token_secret)

    policy_store = PolicyStore()
    policy_store.load_dir(settings.policy_dir)

    key_store = SqliteKeyStore(storage_path=settings.key_store_path)
    rate_limiter = TokenBucketRateLimiter(valkey_client)

    # Resume the chain from the existing log's last hash, if any -- a
    # fresh AuditChain(initial_last_hash=None) after a process restart
    # would otherwise write prev_hash=None into a record appended after
    # real prior history, breaking the chain at every restart.
    audit_chain = AuditChain(
        JsonlSink(settings.audit_log_path), initial_last_hash=read_last_hash(settings.audit_log_path)
    )

    provider = _build_provider(settings)
    fallback_chain = _build_fallback_chain(settings, provider)

    orchestrator = Orchestrator(pii, policy_store, fallback_chain, audit_chain, DETECTOR_VERSIONS, PACK_VERSIONS)

    app.state.settings = settings
    app.state.pii = pii
    app.state.policy_store = policy_store
    app.state.key_store = key_store
    app.state.rate_limiter = rate_limiter
    app.state.fallback_chain = fallback_chain
    app.state.orchestrator = orchestrator
    app.state.valkey_client = valkey_client
    app.state.audit_chain = audit_chain

    yield

    vault_store.close()
    key_store.close()
    if isinstance(provider, (OllamaProvider, OpenAICompatibleProvider)):
        await provider.aclose()


app = FastAPI(title="monoai-gateway-2.0", lifespan=lifespan)
register_auth_exception_handlers(app)

from api import admin as _admin_api  # noqa: E402
from api import chat as _chat_api  # noqa: E402
from api import evidence as _evidence_api  # noqa: E402
from api import health as _health_api  # noqa: E402

app.include_router(_chat_api.router)
app.include_router(_health_api.router)
app.include_router(_evidence_api.router)
app.include_router(_admin_api.router)
