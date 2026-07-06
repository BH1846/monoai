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
    key_store_path: str = field(default_factory=lambda: os.environ.get("GATEWAY_KEY_STORE_PATH", "./gateway_keys.sqlite"))

    # -- audit --
    audit_log_path: str = field(default_factory=lambda: os.environ.get("MONOAI_AUDIT_LOG_PATH", "./gateway_audit.jsonl"))

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
