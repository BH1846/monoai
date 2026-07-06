"""Env-driven settings for mcp-firewall. Deliberately reuses the SAME
env var names as gateway/config.py for vault/Valkey (VALKEY_*,
VAULT_BACKEND, PII_VAULT_STORAGE_PATH, SESSION_TOKEN_SECRET) -- when
co-deployed with the main gateway, a REVERSIBLE-tokenized tool argument
lands in the identical vault namespace a chat session already uses, so
a later turn referencing "what did that command touch" can resolve
through the same VaultStore, not a second disconnected one.
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


@dataclass
class Settings:
    vault_backend: str = field(default_factory=lambda: os.environ.get("VAULT_BACKEND", "sqlite"))
    vault_storage_path: str = field(default_factory=lambda: os.environ.get("PII_VAULT_STORAGE_PATH", "./pii_vault.sqlite"))
    vault_postgres_dsn: str | None = field(default_factory=lambda: os.environ.get("VAULT_POSTGRES_DSN") or None)
    session_token_secret: str = field(default_factory=lambda: os.environ.get("SESSION_TOKEN_SECRET", "dev-only-insecure-secret"))

    valkey_host: str = field(default_factory=lambda: os.environ.get("VALKEY_HOST", "127.0.0.1"))
    valkey_port: int = field(default_factory=lambda: int(os.environ.get("VALKEY_PORT", "6380")))
    valkey_password: str | None = field(default_factory=lambda: os.environ.get("VALKEY_PASSWORD") or None)
    valkey_key_name: str = field(default_factory=lambda: os.environ.get("VALKEY_KEY_NAME", "sentinel:pii_vault:master_key"))

    policy_dir: str = field(default_factory=lambda: os.environ.get("POLICY_DIR", "./policies"))
    tool_rules_path: str = field(default_factory=lambda: os.environ.get("MCP_TOOL_RULES_PATH", ""))
    mcp_upstream_url: str = field(default_factory=lambda: os.environ.get("MCP_UPSTREAM_URL", "http://localhost:9000"))


def load_settings() -> Settings:
    return Settings()
