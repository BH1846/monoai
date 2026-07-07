"""SqliteProviderStore: admin-registered upstream LLM provider credentials
and model->provider mappings. Mirrors auth/store.py's SqliteKeyStore shape
(sqlite, no locking, check_same_thread=False), but encrypts provider API
keys at rest using the existing VaultCrypto primitive (core/vault/crypto.py)
instead of inventing new crypto -- same AES-256-GCM + sealed-box envelope
already used for PII vault entries, keyed here by a fixed AAD namespace
plus the provider_id (binds ciphertext to that specific provider row).
"""
from __future__ import annotations

import secrets
import sqlite3
import time
from dataclasses import dataclass
from typing import Optional

from vault.crypto import VaultCrypto

# Fixed AAD namespace for provider-key encryption (VaultCrypto.encrypt/decrypt
# binds ciphertext to "{session_id}:{token_id}" -- provider keys aren't
# session-scoped, so provider_id alone is the discriminator).
_AAD_NAMESPACE = "provider_registry"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS providers (
    provider_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    base_url TEXT NOT NULL,
    api_key_nonce BLOB,
    api_key_ciphertext BLOB,
    api_key_sealed_dek BLOB,
    key_last4 TEXT,
    enabled INTEGER NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS models (
    model_id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    upstream_model TEXT NOT NULL,
    display_name TEXT NOT NULL,
    enabled INTEGER NOT NULL,
    created_at REAL NOT NULL
);
"""


@dataclass
class ProviderRecord:
    provider_id: str
    name: str
    kind: str
    base_url: str
    key_last4: str | None
    enabled: bool
    created_at: float


@dataclass
class ModelRecord:
    model_id: str
    provider_id: str
    provider_name: str
    upstream_model: str
    display_name: str
    enabled: bool
    created_at: float


@dataclass
class ResolvedModel:
    model_id: str
    provider_id: str
    provider_name: str
    kind: str
    base_url: str
    upstream_model: str
    api_key: str | None


def _row_to_provider(row) -> ProviderRecord:
    provider_id, name, kind, base_url, key_last4, enabled, created_at = row
    return ProviderRecord(
        provider_id=provider_id, name=name, kind=kind, base_url=base_url,
        key_last4=key_last4, enabled=bool(enabled), created_at=created_at,
    )


class SqliteProviderStore:
    def __init__(self, crypto: VaultCrypto, storage_path: str = "./gateway_providers.sqlite") -> None:
        self._crypto = crypto
        self._conn = sqlite3.connect(storage_path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def add_provider(
        self, name: str, kind: str, base_url: str, api_key: str | None = None,
    ) -> ProviderRecord:
        if kind not in ("openai-compatible", "ollama"):
            raise ValueError(f"unknown provider kind: {kind!r} (expected 'openai-compatible' or 'ollama')")
        provider_id = "prov_" + secrets.token_hex(6)
        created_at = time.time()

        nonce = ciphertext = sealed_dek = None
        key_last4 = None
        if api_key:
            nonce, ciphertext, sealed_dek = self._crypto.encrypt(_AAD_NAMESPACE, provider_id, api_key)
            key_last4 = api_key[-4:]

        self._conn.execute(
            "INSERT INTO providers (provider_id, name, kind, base_url, api_key_nonce, "
            "api_key_ciphertext, api_key_sealed_dek, key_last4, enabled, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (provider_id, name, kind, base_url, nonce, ciphertext, sealed_dek, key_last4, 1, created_at),
        )
        self._conn.commit()
        return ProviderRecord(
            provider_id=provider_id, name=name, kind=kind, base_url=base_url,
            key_last4=key_last4, enabled=True, created_at=created_at,
        )

    def get_provider(self, provider_id: str) -> Optional[ProviderRecord]:
        row = self._conn.execute(
            "SELECT provider_id, name, kind, base_url, key_last4, enabled, created_at "
            "FROM providers WHERE provider_id = ?",
            (provider_id,),
        ).fetchone()
        return _row_to_provider(row) if row else None

    def list_providers(self) -> list[ProviderRecord]:
        rows = self._conn.execute(
            "SELECT provider_id, name, kind, base_url, key_last4, enabled, created_at FROM providers"
        ).fetchall()
        return [_row_to_provider(row) for row in rows]

    def delete_provider(self, provider_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM providers WHERE provider_id = ?", (provider_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def get_decrypted_key(self, provider_id: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT api_key_nonce, api_key_ciphertext, api_key_sealed_dek FROM providers WHERE provider_id = ?",
            (provider_id,),
        ).fetchone()
        if row is None or row[0] is None:
            return None
        nonce, ciphertext, sealed_dek = row
        return self._crypto.decrypt(_AAD_NAMESPACE, provider_id, nonce, ciphertext, sealed_dek)

    def add_model(
        self, model_id: str, provider_id: str, upstream_model: str | None = None, display_name: str | None = None,
    ) -> ModelRecord:
        provider = self.get_provider(provider_id)
        if provider is None:
            raise ValueError(f"unknown provider_id: {provider_id!r}")
        upstream_model = upstream_model or model_id
        display_name = display_name or model_id
        created_at = time.time()
        self._conn.execute(
            "INSERT OR REPLACE INTO models (model_id, provider_id, upstream_model, display_name, "
            "enabled, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (model_id, provider_id, upstream_model, display_name, 1, created_at),
        )
        self._conn.commit()
        return ModelRecord(
            model_id=model_id, provider_id=provider_id, provider_name=provider.name,
            upstream_model=upstream_model, display_name=display_name, enabled=True, created_at=created_at,
        )

    def get_model(self, model_id: str) -> Optional[ModelRecord]:
        row = self._conn.execute(
            "SELECT m.model_id, m.provider_id, p.name, m.upstream_model, m.display_name, m.enabled, m.created_at "
            "FROM models m JOIN providers p ON p.provider_id = m.provider_id WHERE m.model_id = ?",
            (model_id,),
        ).fetchone()
        if row is None:
            return None
        model_id_, provider_id, provider_name, upstream_model, display_name, enabled, created_at = row
        return ModelRecord(
            model_id=model_id_, provider_id=provider_id, provider_name=provider_name,
            upstream_model=upstream_model, display_name=display_name, enabled=bool(enabled), created_at=created_at,
        )

    def list_models(self) -> list[ModelRecord]:
        rows = self._conn.execute(
            "SELECT m.model_id, m.provider_id, p.name, m.upstream_model, m.display_name, m.enabled, m.created_at "
            "FROM models m JOIN providers p ON p.provider_id = m.provider_id ORDER BY m.created_at"
        ).fetchall()
        return [
            ModelRecord(
                model_id=r[0], provider_id=r[1], provider_name=r[2], upstream_model=r[3],
                display_name=r[4], enabled=bool(r[5]), created_at=r[6],
            )
            for r in rows
        ]

    def delete_model(self, model_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM models WHERE model_id = ?", (model_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def resolve(self, model_id: str) -> Optional[ResolvedModel]:
        row = self._conn.execute(
            "SELECT m.provider_id, m.upstream_model, p.name, p.kind, p.base_url, p.enabled, m.enabled "
            "FROM models m JOIN providers p ON p.provider_id = m.provider_id WHERE m.model_id = ?",
            (model_id,),
        ).fetchone()
        if row is None:
            return None
        provider_id, upstream_model, provider_name, kind, base_url, provider_enabled, model_enabled = row
        if not provider_enabled or not model_enabled:
            return None
        return ResolvedModel(
            model_id=model_id, provider_id=provider_id, provider_name=provider_name, kind=kind,
            base_url=base_url, upstream_model=upstream_model, api_key=self.get_decrypted_key(provider_id),
        )

    def close(self) -> None:
        self._conn.close()
