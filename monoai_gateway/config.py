"""Env-driven settings for the gateway.

Valkey creds are read by pii_pipeline.vault itself (VALKEY_HOST/PORT/PASSWORD/
KEY_NAME, or a .env next to the SENTINEL-2.0 checkout) -- this module only
covers settings the gateway layer owns: which provider to dispatch to, where
to persist state, and the optional single-key auth.

Also loads this repo's own root .env (API keys / cloud model choices) --
same "real env vars win" precedence as SENTINEL's loader, so CI/production
can still override via real environment variables.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _load_dotenv(path: str = None) -> None:
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


@dataclass
class Settings:
    # -- PII layer --------------------------------------------------------
    vault_storage_path: str = field(
        default_factory=lambda: os.environ.get("PII_VAULT_STORAGE_PATH", "./pii_vault.sqlite")
    )
    # Real ONNX NER model (better recall, e.g. catches lowercase names) vs.
    # the rule-based fallback. Auto-falls back if onnxruntime/tokenizers
    # aren't installed or the model files are missing.
    pii_use_onnx_ner: bool = field(default_factory=lambda: _env_bool("PII_USE_ONNX_NER", True))

    # -- Router / provider layer -------------------------------------------
    # "stub" (tests/demo, no external calls), "ollama" (local inference),
    # "cloud" (any OpenAI-compatible API -- see .env / providers.py).
    provider: str = field(default_factory=lambda: os.environ.get("MONOAI_PROVIDER", "stub"))
    ollama_base_url: str = field(
        default_factory=lambda: os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    router_log_path: str = field(
        default_factory=lambda: os.environ.get("MONOAI_ROUTER_LOG_PATH", "./lite_router_log.jsonl")
    )

    # -- Cloud provider (OpenAICompatibleProvider) --------------------------
    # CLOUD_API_KEY is a fallback shared key; CLOUD_API_KEY_{SIMPLE,MODERATE,
    # COMPLEX} let each difficulty tier use its own key (e.g. three separate
    # per-model OpenRouter keys) -- per-tier key wins when both are set.
    cloud_api_base_url: str = field(default_factory=lambda: os.environ.get("CLOUD_API_BASE_URL", ""))
    cloud_api_key: str | None = field(default_factory=lambda: os.environ.get("CLOUD_API_KEY") or None)
    cloud_provider_name: str = field(default_factory=lambda: os.environ.get("CLOUD_PROVIDER_NAME", "cloud"))
    cloud_model_simple: str = field(default_factory=lambda: os.environ.get("CLOUD_MODEL_SIMPLE", ""))
    cloud_model_moderate: str = field(default_factory=lambda: os.environ.get("CLOUD_MODEL_MODERATE", ""))
    cloud_model_complex: str = field(default_factory=lambda: os.environ.get("CLOUD_MODEL_COMPLEX", ""))
    cloud_api_key_simple: str | None = field(default_factory=lambda: os.environ.get("CLOUD_API_KEY_SIMPLE") or None)
    cloud_api_key_moderate: str | None = field(
        default_factory=lambda: os.environ.get("CLOUD_API_KEY_MODERATE") or None
    )
    cloud_api_key_complex: str | None = field(
        default_factory=lambda: os.environ.get("CLOUD_API_KEY_COMPLEX") or None
    )

    # -- Gateway ------------------------------------------------------------
    audit_log_path: str = field(
        default_factory=lambda: os.environ.get("MONOAI_AUDIT_LOG_PATH", "./gateway_audit.jsonl")
    )
    # If set, requests must send `Authorization: Bearer <this value>`.
    bearer_token: str | None = field(default_factory=lambda: os.environ.get("MONOAI_BEARER_TOKEN") or None)


def load_settings() -> Settings:
    return Settings()
