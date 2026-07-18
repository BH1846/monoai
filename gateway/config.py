"""Env-driven settings. Extends monoai_gateway/config.py's pattern
(setdefault-based .env loader, real env vars always win) with the new
Phase 1 fields: admin key, redis/valkey url, key-store path, policy dir,
session-token secret, and per-tier fallback-chain config.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _load_dotenv(path: str | None = None) -> None:
    path = path or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.isfile(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_list(name: str, default: list[str]) -> list[str]:
    val = os.environ.get(name)
    if val is None:
        return default
    return [x.strip() for x in val.split(",") if x.strip()]


@dataclass
class Settings:
    # -- vault / detection --
    vault_backend: str = field(default_factory=lambda: os.environ.get("VAULT_BACKEND", "sqlite"))
    vault_storage_path: str = field(default_factory=lambda: os.environ.get("PII_VAULT_STORAGE_PATH", "./pii_vault.sqlite"))
    vault_postgres_dsn: str | None = field(default_factory=lambda: os.environ.get("VAULT_POSTGRES_DSN") or None)
    vault_ttl_s: float | None = field(default_factory=lambda: float(v) if (v := os.environ.get("VAULT_TTL_S")) else None)
    pii_use_onnx_ner: bool = field(default_factory=lambda: _env_bool("PII_USE_ONNX_NER", True))
    session_token_secret: str = field(default_factory=lambda: os.environ.get("SESSION_TOKEN_SECRET", "dev-only-insecure-secret"))

    # -- audit sink (G10): jsonl (default) | postgres | webhook --
    audit_sink: str = field(default_factory=lambda: os.environ.get("AUDIT_SINK", "jsonl"))
    audit_postgres_dsn: str | None = field(default_factory=lambda: os.environ.get("AUDIT_POSTGRES_DSN") or None)
    audit_webhook_url: str | None = field(default_factory=lambda: os.environ.get("AUDIT_WEBHOOK_URL") or None)
    audit_signing_key_name: str = field(default_factory=lambda: os.environ.get("AUDIT_SIGNING_KEY_NAME", "monoai:audit:signing_key"))

    # -- per-record tamper-evident signing (G13) --
    audit_sign_enabled: bool = field(default_factory=lambda: _env_bool("MONOAI_AUDIT_SIGN", False))
    audit_sign_key: str | None = field(default_factory=lambda: os.environ.get("MONOAI_AUDIT_SIGN_KEY") or None)

    # -- Tier 2.5 semantic injection judge (G4) --
    llm_judge_enabled: bool = field(default_factory=lambda: _env_bool("MONOAI_ENABLE_LLM_JUDGE", False))
    llm_judge_ollama_model: str = field(default_factory=lambda: os.environ.get("MONOAI_LLM_JUDGE_MODEL", "qwen2.5:7b"))
    llm_judge_claude_api_key: str | None = field(default_factory=lambda: os.environ.get("MONOAI_LLM_JUDGE_CLAUDE_API_KEY") or None)
    llm_judge_claude_model: str = field(default_factory=lambda: os.environ.get("MONOAI_LLM_JUDGE_CLAUDE_MODEL", "claude-haiku-4-5-20251001"))
    llm_judge_timeout_s: float = field(default_factory=lambda: float(os.environ.get("MONOAI_LLM_JUDGE_TIMEOUT_S", "5")))

    # -- valkey (vault master key + rate limiter) --
    valkey_host: str = field(default_factory=lambda: os.environ.get("VALKEY_HOST", "127.0.0.1"))
    valkey_port: int = field(default_factory=lambda: int(os.environ.get("VALKEY_PORT", "6380")))
    valkey_password: str | None = field(default_factory=lambda: os.environ.get("VALKEY_PASSWORD") or None)
    valkey_key_name: str = field(default_factory=lambda: os.environ.get("VALKEY_KEY_NAME", "sentinel:pii_vault:master_key"))

    # -- policy --
    policy_dir: str = field(default_factory=lambda: os.environ.get("POLICY_DIR", "./policies"))
    default_policy_id: str = field(default_factory=lambda: os.environ.get("DEFAULT_POLICY_ID", "default"))

    # -- auth --
    admin_key: str | None = field(default_factory=lambda: os.environ.get("MONOAI_ADMIN_KEY") or None)
    key_store_backend: str = field(default_factory=lambda: os.environ.get("KEY_STORE_BACKEND", "sqlite"))
    key_store_path: str = field(default_factory=lambda: os.environ.get("GATEWAY_KEY_STORE_PATH", "./gateway_keys.sqlite"))
    key_store_postgres_dsn: str | None = field(default_factory=lambda: os.environ.get("KEY_STORE_POSTGRES_DSN") or None)
    provider_store_path: str = field(default_factory=lambda: os.environ.get("PROVIDER_STORE_PATH", "./gateway_providers.sqlite"))
    admin_account_store_path: str = field(default_factory=lambda: os.environ.get("ADMIN_ACCOUNT_STORE_PATH", "./gateway_admin_accounts.sqlite"))
    user_account_store_path: str = field(default_factory=lambda: os.environ.get("USER_ACCOUNT_STORE_PATH", "./gateway_user_accounts.sqlite"))
    # Per-request prompt/reply store backing the admin Users-tab drill-down
    # (gateway/auth/transaction_store.py). Raw text is vault-encrypted at rest.
    transaction_store_path: str = field(default_factory=lambda: os.environ.get("TRANSACTION_STORE_PATH", "./gateway_transactions.sqlite"))
    # Default monthly budget cap auto-applied to self-registered accounts
    # (POST /v1/auth/register) -- admin-created keys via /v1/admin/keys are
    # unaffected. Keeps unauthenticated self-signup from being a blank check
    # against upstream LLM spend; set to "" / 0 for no cap.
    self_serve_budget_usd_monthly: float | None = field(
        default_factory=lambda: float(v) if (v := os.environ.get("SELF_SERVE_BUDGET_USD_MONTHLY", "20")) else None
    )

    # -- audit --
    audit_log_path: str = field(default_factory=lambda: os.environ.get("MONOAI_AUDIT_LOG_PATH", "./gateway_audit.jsonl"))

    # -- audit forwarding (peer gateway -> manager gateway) --
    # Every operator runs their own full, independent gateway; one instance is
    # additionally treated as the "manager" whose Audit Log is the aggregate
    # view. Setting MONOAI_AUDIT_FORWARD_URL turns THIS instance into a
    # forwarder: its records are still written locally first (unchanged), then
    # shipped to the manager out-of-band. Unset = off, and nothing about the
    # local audit path changes.
    #
    # Manager downtime can never affect local chat: forwarding is buffered on
    # disk and retried on a background thread (core/audit/sinks.py).
    audit_forward_url: str | None = field(default_factory=lambda: os.environ.get("MONOAI_AUDIT_FORWARD_URL") or None)
    # The MANAGER's MONOAI_ADMIN_KEY -- trusted gateway-to-gateway shared key.
    audit_forward_admin_key: str | None = field(default_factory=lambda: os.environ.get("MONOAI_AUDIT_FORWARD_ADMIN_KEY") or None)
    audit_forward_queue_path: str = field(default_factory=lambda: os.environ.get("MONOAI_AUDIT_FORWARD_QUEUE_PATH", "./gateway_audit_forward_queue.sqlite"))
    audit_forward_interval_s: float = field(default_factory=lambda: float(os.environ.get("MONOAI_AUDIT_FORWARD_INTERVAL_S", "30")))
    audit_forward_timeout_s: float = field(default_factory=lambda: float(os.environ.get("MONOAI_AUDIT_FORWARD_TIMEOUT_S", "5")))
    # Stamped onto forwarded records as `origin_gateway` so the manager's
    # Audit Log can tell whose instance a record came from.
    gateway_id: str = field(default_factory=lambda: os.environ.get("MONOAI_GATEWAY_ID") or os.uname().nodename)
    # Manager side: record_ids already ingested, so at-least-once retries
    # don't double-append (see gateway/audit_dedupe.py).
    audit_ingest_dedupe_path: str = field(default_factory=lambda: os.environ.get("MONOAI_AUDIT_INGEST_DEDUPE_PATH", "./gateway_audit_ingest.sqlite"))

    # -- virtual-key federation (sibling of audit forwarding) --
    # Reuses the audit-forwarding config: a gateway that forwards audit
    # (MONOAI_AUDIT_FORWARD_URL set) also forwards its key create/revoke events
    # to the same manager, so keys show in the manager's Users tab. The keys
    # ingest URL is DERIVED from the audit one (see key_forward_url) -- no new
    # user-facing URL var. MONOAI_GATEWAY_CALLBACK_URL is genuinely new: it is
    # this gateway's own reachable base URL, advertised so a manager can push a
    # revoke BACK here (reverse propagation). Unset -> this gateway's forwarded
    # keys are visible on the manager but not remotely revocable.
    gateway_callback_url: str | None = field(default_factory=lambda: os.environ.get("MONOAI_GATEWAY_CALLBACK_URL") or None)
    # Internal state paths (not user-facing knobs; defaults are fine).
    key_forward_queue_path: str = field(default_factory=lambda: os.environ.get("MONOAI_KEY_FORWARD_QUEUE_PATH", "./gateway_key_forward_queue.sqlite"))
    key_reverse_queue_path: str = field(default_factory=lambda: os.environ.get("MONOAI_KEY_REVERSE_QUEUE_PATH", "./gateway_key_reverse_queue.sqlite"))
    key_ingest_dedupe_path: str = field(default_factory=lambda: os.environ.get("MONOAI_KEY_INGEST_DEDUPE_PATH", "./gateway_key_ingest.sqlite"))
    key_revoke_ingest_dedupe_path: str = field(default_factory=lambda: os.environ.get("MONOAI_KEY_REVOKE_INGEST_DEDUPE_PATH", "./gateway_key_revoke_ingest.sqlite"))

    # -- provider/model config sync (manager -> instance; the DOWNWARD flow) --
    # A forwarding instance PULLS the manager's provider/model registry (the
    # manager is the single source of truth). Reuses the audit-forwarding
    # config: enabled when MONOAI_AUDIT_FORWARD_URL + admin key are set; the
    # sync URL is DERIVED (see provider_sync_url) -- no new URL var. The
    # instance's X25519 Box keypair (for receiving sealed API keys) lives in
    # Valkey under its own name.
    provider_sync_interval_s: float = field(default_factory=lambda: float(os.environ.get("MONOAI_PROVIDER_SYNC_INTERVAL_S", "60")))
    provider_sync_key_name: str = field(default_factory=lambda: os.environ.get("MONOAI_PROVIDER_SYNC_KEY_NAME", "monoai:provider_sync:instance_key"))

    @property
    def key_forward_url(self) -> str | None:
        """The manager's key-ingest URL, derived from the audit-forward URL so
        no separate env var is needed (both point at the same manager)."""
        if not self.audit_forward_url:
            return None
        from urllib.parse import urlsplit, urlunsplit
        parts = urlsplit(self.audit_forward_url)
        return urlunsplit((parts.scheme, parts.netloc, "/v1/admin/keys/ingest", "", ""))

    @property
    def provider_sync_url(self) -> str | None:
        """The manager's provider-sync URL, derived from the audit-forward URL
        (same manager). None on a non-forwarding gateway (nothing to pull)."""
        if not self.audit_forward_url:
            return None
        from urllib.parse import urlsplit, urlunsplit
        parts = urlsplit(self.audit_forward_url)
        return urlunsplit((parts.scheme, parts.netloc, "/v1/admin/providers/sync", "", ""))

    # -- agent registry (Wazuh-style manager/agent split) --
    # The manager (this gateway) is the enrollment authority + audit sink for
    # remote SENTINEL agents. Its agent-channel keypair lives in Valkey under
    # a name DISTINCT from the vault master key -- separate trust domains.
    agent_store_path: str = field(default_factory=lambda: os.environ.get("AGENT_STORE_PATH", "./gateway_agents.sqlite"))
    agent_channel_key_name: str = field(default_factory=lambda: os.environ.get("AGENT_CHANNEL_KEY_NAME", "monoai:agent_channel:manager_key"))
    agent_enroll_token_ttl_s: float = field(default_factory=lambda: float(os.environ.get("AGENT_ENROLL_TOKEN_TTL_S", "3600")))
    agent_heartbeat_interval_s: float = field(default_factory=lambda: float(os.environ.get("AGENT_HEARTBEAT_INTERVAL_S", "30")))
    agent_missed_beats_offline: int = field(default_factory=lambda: int(os.environ.get("AGENT_MISSED_BEATS_OFFLINE", "3")))

    # -- provider --
    provider: str = field(default_factory=lambda: os.environ.get("MONOAI_PROVIDER", "stub"))
    ollama_base_url: str = field(default_factory=lambda: os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"))
    cloud_api_base_url: str = field(default_factory=lambda: os.environ.get("CLOUD_API_BASE_URL", ""))
    cloud_provider_name: str = field(default_factory=lambda: os.environ.get("CLOUD_PROVIDER_NAME", "cloud"))
    cloud_api_key: str | None = field(default_factory=lambda: os.environ.get("CLOUD_API_KEY") or None)
    cloud_model_simple: str = field(default_factory=lambda: os.environ.get("CLOUD_MODEL_SIMPLE", ""))
    cloud_model_moderate: str = field(default_factory=lambda: os.environ.get("CLOUD_MODEL_MODERATE", ""))
    cloud_model_complex: str = field(default_factory=lambda: os.environ.get("CLOUD_MODEL_COMPLEX", ""))
    cloud_api_key_simple: str | None = field(default_factory=lambda: os.environ.get("CLOUD_API_KEY_SIMPLE") or None)
    cloud_api_key_moderate: str | None = field(default_factory=lambda: os.environ.get("CLOUD_API_KEY_MODERATE") or None)
    cloud_api_key_complex: str | None = field(default_factory=lambda: os.environ.get("CLOUD_API_KEY_COMPLEX") or None)

    # -- OTEL observability (G9) --
    otel_exporter_otlp_endpoint: str | None = field(default_factory=lambda: os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or None)
    otel_service_name: str = field(default_factory=lambda: os.environ.get("OTEL_SERVICE_NAME", "monoai-gateway"))

    # -- circuit breaker / retry (per fallback route) --
    circuit_failure_threshold: int = field(default_factory=lambda: int(os.environ.get("CIRCUIT_FAILURE_THRESHOLD", "5")))
    circuit_open_duration_s: float = field(default_factory=lambda: float(os.environ.get("CIRCUIT_OPEN_DURATION_S", "30")))
    max_retries_per_route: int = field(default_factory=lambda: int(os.environ.get("MAX_RETRIES_PER_ROUTE", "2")))


def load_settings() -> Settings:
    return Settings()
