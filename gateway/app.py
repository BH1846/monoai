"""FastAPI surface: POST /v1/chat/completions, /health/live, /health/ready,
GET /v1/evidence/export, /v1/admin/* (key-store CRUD + policy reload).
Extends monoai_gateway/app.py's lifespan-wiring pattern with auth,
streaming, the new core/ modules, and per-tier provider fallback chains.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import redis
from agents.keys import load_or_create_manager_keypair
from agents.store import SqliteAgentStore
from audit.chain import AuditChain
from audit.sinks import JsonlSink, PostgresSink, WebhookSink, read_last_hash
from audit.signer import load_signing_key as load_record_signing_key
from audit.signing import load_or_create_signing_key
from auth.admin_account_store import SqliteAdminAccountStore
from auth.middleware import register_auth_exception_handlers
from auth.postgres_key_store import PostgresKeyStore
from auth.rate_limit import TokenBucketRateLimiter
from auth.store import KeyStore, SqliteKeyStore
from auth.transaction_store import SqliteTransactionStore
from auth.user_account_store import SqliteUserAccountStore
from config import Settings, load_settings
from detect.pipeline import DetectionPipeline
from detect.stages.injection_judge import SemanticInjectionJudge
from fastapi import FastAPI
from orchestrator import Orchestrator
from pii import PiiEngine
from policy.store import PolicyStore
from providers.base import ProviderAdapter
from providers.dynamic_router import DynamicProviderRouter
from providers.fallback_chain import FallbackChain, Route
from providers.ollama import OllamaProvider
from providers.openai_compatible import CloudRoute, OpenAICompatibleProvider
from providers.registry_store import SqliteProviderStore
from providers.stub import StubProvider
from vault.crypto import VaultCrypto
from vault.storage.base import VaultStore
from vault.storage.postgres_store import PostgresVaultStore
from vault.storage.sqlite_store import SqliteVaultStore

DETECTOR_VERSIONS = {"regex": "base_en-v1", "secrets": "base_en-v1", "ner": "base_en-v1", "locked_span": "base_en-v1"}
PACK_VERSIONS = {"base_en": "base_en-v1", "gulf_ar": "gulf_ar-v1"}


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


def _build_vault_store(settings: Settings, vault_crypto: VaultCrypto) -> VaultStore:
    if settings.vault_backend == "postgres":
        if not settings.vault_postgres_dsn:
            raise ValueError("VAULT_BACKEND=postgres requires VAULT_POSTGRES_DSN")
        return PostgresVaultStore(vault_crypto, settings.vault_postgres_dsn, default_ttl_s=settings.vault_ttl_s)
    return SqliteVaultStore(vault_crypto, storage_path=settings.vault_storage_path, default_ttl_s=settings.vault_ttl_s)


def _build_key_store(settings: Settings) -> KeyStore:
    if settings.key_store_backend == "postgres":
        if not settings.key_store_postgres_dsn:
            raise ValueError("KEY_STORE_BACKEND=postgres requires KEY_STORE_POSTGRES_DSN")
        return PostgresKeyStore(settings.key_store_postgres_dsn)
    return SqliteKeyStore(storage_path=settings.key_store_path)


def _build_audit_sink(settings: Settings):
    if settings.audit_sink == "postgres":
        if not settings.audit_postgres_dsn:
            raise ValueError("AUDIT_SINK=postgres requires AUDIT_POSTGRES_DSN")
        return PostgresSink(settings.audit_postgres_dsn)
    if settings.audit_sink == "webhook":
        if not settings.audit_webhook_url:
            raise ValueError("AUDIT_SINK=webhook requires AUDIT_WEBHOOK_URL")
        return WebhookSink(settings.audit_webhook_url)
    return JsonlSink(settings.audit_log_path)


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
    vault_store = _build_vault_store(settings, vault_crypto)
    semantic_judge = SemanticInjectionJudge(
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.llm_judge_ollama_model,
        claude_api_key=settings.llm_judge_claude_api_key,
        claude_model=settings.llm_judge_claude_model,
        timeout_s=settings.llm_judge_timeout_s,
    )
    pii = PiiEngine(
        pipeline, vault_store, settings.session_token_secret,
        semantic_judge=semantic_judge, llm_judge_enabled=settings.llm_judge_enabled,
    )

    policy_store = PolicyStore()
    policy_store.load_dir(settings.policy_dir)

    key_store = _build_key_store(settings)
    rate_limiter = TokenBucketRateLimiter(valkey_client)

    audit_sink = _build_audit_sink(settings)
    # Resume the chain from the existing log's last hash, if any -- a
    # fresh AuditChain(initial_last_hash=None) after a process restart
    # would otherwise write prev_hash=None into a record appended after
    # real prior history, breaking the chain at every restart.
    initial_last_hash = None
    if isinstance(audit_sink, JsonlSink):
        initial_last_hash = read_last_hash(settings.audit_log_path)
    elif isinstance(audit_sink, PostgresSink):
        existing = audit_sink.read_all()
        initial_last_hash = existing[-1].hash if existing else None
    record_signing_key = None
    if settings.audit_sign_enabled:
        record_signing_key = load_record_signing_key(settings.audit_sign_key, settings.session_token_secret)
    audit_chain = AuditChain(audit_sink, initial_last_hash=initial_last_hash, signing_key=record_signing_key)

    signing_key = load_or_create_signing_key(valkey_client, key_name=settings.audit_signing_key_name)

    provider = _build_provider(settings)
    fallback_chain = _build_fallback_chain(settings, provider)

    provider_store = SqliteProviderStore(vault_crypto, storage_path=settings.provider_store_path)
    dynamic_router = DynamicProviderRouter(provider_store)
    admin_account_store = SqliteAdminAccountStore(vault_crypto, storage_path=settings.admin_account_store_path)
    user_account_store = SqliteUserAccountStore(vault_crypto, storage_path=settings.user_account_store_path)
    transaction_store = SqliteTransactionStore(vault_crypto, storage_path=settings.transaction_store_path)

    # Manager/agent split: agent registry (no vault_crypto dependency -- it
    # stores agent PUBLIC keys only) + the manager's own agent-channel
    # keypair, kept in Valkey under a name distinct from the vault master key.
    agent_store = SqliteAgentStore(
        storage_path=settings.agent_store_path,
        heartbeat_interval_s=settings.agent_heartbeat_interval_s,
        missed_beats_offline=settings.agent_missed_beats_offline,
    )
    manager_agent_key = load_or_create_manager_keypair(valkey_client, key_name=settings.agent_channel_key_name)

    orchestrator = Orchestrator(
        pii, policy_store, fallback_chain, audit_chain, DETECTOR_VERSIONS, PACK_VERSIONS,
        dynamic_router=dynamic_router, transaction_store=transaction_store,
    )

    app.state.settings = settings
    app.state.pii = pii
    app.state.detection_pipeline = pipeline
    app.state.vault_store = vault_store
    app.state.policy_store = policy_store
    app.state.key_store = key_store
    app.state.rate_limiter = rate_limiter
    app.state.fallback_chain = fallback_chain
    app.state.orchestrator = orchestrator
    app.state.valkey_client = valkey_client
    app.state.audit_chain = audit_chain
    app.state.signing_key = signing_key
    app.state.provider_store = provider_store
    app.state.admin_account_store = admin_account_store
    app.state.user_account_store = user_account_store
    app.state.transaction_store = transaction_store
    app.state.agent_store = agent_store
    app.state.manager_agent_key = manager_agent_key

    yield

    vault_store.close()
    key_store.close()
    provider_store.close()
    admin_account_store.close()
    user_account_store.close()
    agent_store.close()
    await dynamic_router.aclose()
    if isinstance(provider, (OllamaProvider, OpenAICompatibleProvider)):
        await provider.aclose()


from config import load_settings as _load_settings_for_otel  # noqa: E402
from obs.otel import configure_otel  # noqa: E402

_otel_settings = _load_settings_for_otel()
configure_otel(
    otlp_endpoint=_otel_settings.otel_exporter_otlp_endpoint,
    service_name=_otel_settings.otel_service_name,
)

app = FastAPI(title="monoai-gateway-2.0", lifespan=lifespan)
register_auth_exception_handlers(app)

from api import admin as _admin_api  # noqa: E402
from api import agents as _agents_api  # noqa: E402
from api import auth as _auth_api  # noqa: E402
from api import chat as _chat_api  # noqa: E402
from api import evidence as _evidence_api  # noqa: E402
from api import files as _files_api  # noqa: E402
from api import health as _health_api  # noqa: E402
from api import metrics as _metrics_api  # noqa: E402

app.include_router(_chat_api.router)
app.include_router(_health_api.router)
app.include_router(_evidence_api.router)
app.include_router(_files_api.router)
app.include_router(_admin_api.router)
app.include_router(_agents_api.router)
app.include_router(_auth_api.router)
app.include_router(_metrics_api.router)
