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
from audit.forward_queue import SqliteForwardQueue
from audit.signer import load_signing_key as load_record_signing_key
from audit.signing import load_or_create_signing_key
from audit.sinks import FanoutSink, ForwardingSink, JsonlSink, PostgresSink, WebhookSink, read_last_hash
from audit_dedupe import SqliteIngestDedupe
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
from key_forwarder import KeyEventForwarder
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


def _build_primary_audit_sink(settings: Settings):
    if settings.audit_sink == "postgres":
        if not settings.audit_postgres_dsn:
            raise ValueError("AUDIT_SINK=postgres requires AUDIT_POSTGRES_DSN")
        return PostgresSink(settings.audit_postgres_dsn)
    if settings.audit_sink == "webhook":
        if not settings.audit_webhook_url:
            raise ValueError("AUDIT_SINK=webhook requires AUDIT_WEBHOOK_URL")
        return WebhookSink(settings.audit_webhook_url)
    return JsonlSink(settings.audit_log_path)


def _wrap_audit_sink_for_forwarding(settings: Settings, primary):
    """Optionally fan the primary (local, durable) sink out to a
    ForwardingSink that ships records to a peer "manager" gateway.

    Forwarding is purely additive: the local sink stays first and unchanged,
    so nothing about local audit durability -- or the chat path -- depends on
    the manager being reachable. Unset MONOAI_AUDIT_FORWARD_URL = the primary
    sink is returned untouched.
    """
    if not settings.audit_forward_url:
        return primary
    if not settings.audit_forward_admin_key:
        raise ValueError("MONOAI_AUDIT_FORWARD_URL requires MONOAI_AUDIT_FORWARD_ADMIN_KEY (the manager's admin key)")
    forwarding = ForwardingSink(
        url=settings.audit_forward_url,
        admin_key=settings.audit_forward_admin_key,
        queue=SqliteForwardQueue(settings.audit_forward_queue_path),
        gateway_id=settings.gateway_id,
        interval_s=settings.audit_forward_interval_s,
        timeout=settings.audit_forward_timeout_s,
    )
    return FanoutSink([primary, forwarding])


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

    # Build the PRIMARY sink first and bootstrap last_hash from it, THEN wrap
    # it for forwarding. Order matters: these isinstance checks must see the
    # real local sink, not a FanoutSink wrapper -- otherwise neither branch
    # matches, initial_last_hash silently stays None, and the chain breaks at
    # every restart (the exact bug read_last_hash exists to prevent).
    primary_audit_sink = _build_primary_audit_sink(settings)
    # Resume the chain from the existing log's last hash, if any -- a
    # fresh AuditChain(initial_last_hash=None) after a process restart
    # would otherwise write prev_hash=None into a record appended after
    # real prior history, breaking the chain at every restart.
    initial_last_hash = None
    if isinstance(primary_audit_sink, JsonlSink):
        initial_last_hash = read_last_hash(settings.audit_log_path)
    elif isinstance(primary_audit_sink, PostgresSink):
        existing = primary_audit_sink.read_all()
        initial_last_hash = existing[-1].hash if existing else None
    audit_sink = _wrap_audit_sink_for_forwarding(settings, primary_audit_sink)
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

    # Manager side of audit forwarding: remembers record_ids already ingested
    # from peer gateways so an at-least-once retry can't double-append.
    audit_ingest_dedupe = SqliteIngestDedupe(storage_path=settings.audit_ingest_dedupe_path)

    # Virtual-key federation (sibling of audit forwarding). Gated on the shared
    # federation admin key: a gateway with no MONOAI_AUDIT_FORWARD_ADMIN_KEY
    # doesn't participate and gets none of this (no threads, no state files).
    #   * key_forwarder         -- forward local create/revoke to the manager
    #                              (only if this gateway forwards, i.e. a URL is set)
    #   * key_reverse_forwarder -- push manager-side revokes back to origins
    #                              (per-event target URL)
    #   * the two dedupe stores -- idempotent receive for the two ingest routes
    key_forwarder = None
    key_reverse_forwarder = None
    key_ingest_dedupe = None
    key_revoke_ingest_dedupe = None
    if settings.audit_forward_admin_key:
        key_ingest_dedupe = SqliteIngestDedupe(storage_path=settings.key_ingest_dedupe_path)
        key_revoke_ingest_dedupe = SqliteIngestDedupe(storage_path=settings.key_revoke_ingest_dedupe_path)
        key_reverse_forwarder = KeyEventForwarder(
            admin_key=settings.audit_forward_admin_key,
            queue=SqliteForwardQueue(settings.key_reverse_queue_path),
            default_url=None,  # reverse events carry a per-event _target_url
            interval_s=settings.audit_forward_interval_s,
            timeout=settings.audit_forward_timeout_s,
        )
        if settings.key_forward_url:  # only when this gateway actually forwards
            key_forwarder = KeyEventForwarder(
                admin_key=settings.audit_forward_admin_key,
                queue=SqliteForwardQueue(settings.key_forward_queue_path),
                default_url=settings.key_forward_url,
                interval_s=settings.audit_forward_interval_s,
                timeout=settings.audit_forward_timeout_s,
            )

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
    app.state.audit_ingest_dedupe = audit_ingest_dedupe
    app.state.key_forwarder = key_forwarder
    app.state.key_reverse_forwarder = key_reverse_forwarder
    app.state.key_ingest_dedupe = key_ingest_dedupe
    app.state.key_revoke_ingest_dedupe = key_revoke_ingest_dedupe

    yield

    vault_store.close()
    key_store.close()
    provider_store.close()
    admin_account_store.close()
    user_account_store.close()
    agent_store.close()
    audit_ingest_dedupe.close()
    for _closable in (key_forwarder, key_reverse_forwarder, key_ingest_dedupe, key_revoke_ingest_dedupe):
        if _closable is not None:
            _closable.close()
    # Stops the forwarding worker thread + closes its queue/client. Sinks
    # were previously never closed; that leaked WebhookSink's httpx client
    # and would now leave the forwarder thread running past shutdown.
    _close_audit_sink = getattr(audit_sink, "close", None)
    if _close_audit_sink is not None:
        _close_audit_sink()
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
