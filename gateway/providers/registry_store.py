"""SqliteProviderStore: admin-registered upstream LLM provider credentials
and model->provider mappings. Mirrors auth/store.py's SqliteKeyStore shape
(sqlite, check_same_thread=False), but encrypts provider API keys at rest
using the existing VaultCrypto primitive (core/vault/crypto.py) instead of
inventing new crypto -- same AES-256-GCM + sealed-box envelope already used
for PII vault entries, keyed here by a fixed AAD namespace plus the
provider_id (binds ciphertext to that specific provider row).

`origin_gateway` marks rows that were pulled from a manager gateway by the
provider-sync feature (gateway/provider_sync.py): NULL = configured locally
on this instance, set = mirrored from the manager. A RLock guards the shared
connection because provider sync writes from a background thread while chat
requests read via resolve() on the event loop -- same request-thread-vs-
background-thread concern the audit forward_queue solved with a lock.
"""
from __future__ import annotations

import secrets
import sqlite3
import threading
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
    created_at REAL NOT NULL,
    origin_gateway TEXT
);
CREATE TABLE IF NOT EXISTS models (
    model_id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    upstream_model TEXT NOT NULL,
    display_name TEXT NOT NULL,
    enabled INTEGER NOT NULL,
    created_at REAL NOT NULL,
    origin_gateway TEXT
);
"""

_PROVIDER_COLS = "provider_id, name, kind, base_url, key_last4, enabled, created_at, origin_gateway"


@dataclass
class ProviderRecord:
    provider_id: str
    name: str
    kind: str
    base_url: str
    key_last4: str | None
    enabled: bool
    created_at: float
    origin_gateway: str | None = None


@dataclass
class ModelRecord:
    model_id: str
    provider_id: str
    provider_name: str
    upstream_model: str
    display_name: str
    enabled: bool
    created_at: float
    origin_gateway: str | None = None


@dataclass
class ResolvedModel:
    model_id: str
    provider_id: str
    provider_name: str
    kind: str
    base_url: str
    upstream_model: str
    api_key: str | None


@dataclass
class SyncProvider:
    """A provider as delivered by a manager to a syncing instance -- carries
    the PLAINTEXT api_key (already Box-opened by provider_sync), which this
    store re-encrypts under its OWN VaultCrypto on insert."""
    provider_id: str
    name: str
    kind: str
    base_url: str
    api_key: str | None
    enabled: bool
    created_at: float


@dataclass
class SyncModel:
    model_id: str
    provider_id: str
    upstream_model: str
    display_name: str
    enabled: bool
    created_at: float


def _row_to_provider(row) -> ProviderRecord:
    provider_id, name, kind, base_url, key_last4, enabled, created_at, origin_gateway = row
    return ProviderRecord(
        provider_id=provider_id, name=name, kind=kind, base_url=base_url,
        key_last4=key_last4, enabled=bool(enabled), created_at=created_at, origin_gateway=origin_gateway,
    )


class SqliteProviderStore:
    def __init__(self, crypto: VaultCrypto, storage_path: str = "./gateway_providers.sqlite") -> None:
        self._crypto = crypto
        self._conn = sqlite3.connect(storage_path, check_same_thread=False)
        # RLock (re-entrant): add_model -> get_provider both lock; a plain
        # Lock would deadlock. Guards the shared connection against concurrent
        # use by request threads (resolve) and the provider-sync thread.
        self._lock = threading.RLock()
        self._conn.executescript(_SCHEMA)
        self._ensure_origin_gateway_columns()
        self._conn.commit()

    def _ensure_origin_gateway_columns(self) -> None:
        """Add origin_gateway to tables created before it existed, in place
        (mirrors auth/store.py's _ensure_federation_columns / vault's
        _ensure_expires_at_column) so an existing gateway_providers.sqlite
        upgrades instead of a SELECT crashing on the missing column."""
        for table in ("providers", "models"):
            cols = {r[1] for r in self._conn.execute(f"PRAGMA table_info({table})")}
            if "origin_gateway" not in cols:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN origin_gateway TEXT")

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

        with self._lock:
            self._conn.execute(
                "INSERT INTO providers (provider_id, name, kind, base_url, api_key_nonce, "
                "api_key_ciphertext, api_key_sealed_dek, key_last4, enabled, created_at, origin_gateway) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (provider_id, name, kind, base_url, nonce, ciphertext, sealed_dek, key_last4, 1, created_at),
            )
            self._conn.commit()
        return ProviderRecord(
            provider_id=provider_id, name=name, kind=kind, base_url=base_url,
            key_last4=key_last4, enabled=True, created_at=created_at, origin_gateway=None,
        )

    def get_provider(self, provider_id: str) -> Optional[ProviderRecord]:
        with self._lock:
            row = self._conn.execute(
                f"SELECT {_PROVIDER_COLS} FROM providers WHERE provider_id = ?",
                (provider_id,),
            ).fetchone()
        return _row_to_provider(row) if row else None

    def list_providers(self) -> list[ProviderRecord]:
        with self._lock:
            rows = self._conn.execute(f"SELECT {_PROVIDER_COLS} FROM providers").fetchall()
        return [_row_to_provider(row) for row in rows]

    def delete_provider(self, provider_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM providers WHERE provider_id = ?", (provider_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def get_decrypted_key(self, provider_id: str) -> Optional[str]:
        with self._lock:
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
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO models (model_id, provider_id, upstream_model, display_name, "
                "enabled, created_at, origin_gateway) VALUES (?, ?, ?, ?, ?, ?, NULL)",
                (model_id, provider_id, upstream_model, display_name, 1, created_at),
            )
            self._conn.commit()
        return ModelRecord(
            model_id=model_id, provider_id=provider_id, provider_name=provider.name,
            upstream_model=upstream_model, display_name=display_name, enabled=True,
            created_at=created_at, origin_gateway=None,
        )

    def get_model(self, model_id: str) -> Optional[ModelRecord]:
        with self._lock:
            row = self._conn.execute(
                "SELECT m.model_id, m.provider_id, p.name, m.upstream_model, m.display_name, m.enabled, "
                "m.created_at, m.origin_gateway "
                "FROM models m JOIN providers p ON p.provider_id = m.provider_id WHERE m.model_id = ?",
                (model_id,),
            ).fetchone()
        if row is None:
            return None
        model_id_, provider_id, provider_name, upstream_model, display_name, enabled, created_at, origin_gateway = row
        return ModelRecord(
            model_id=model_id_, provider_id=provider_id, provider_name=provider_name,
            upstream_model=upstream_model, display_name=display_name, enabled=bool(enabled),
            created_at=created_at, origin_gateway=origin_gateway,
        )

    def list_models(self) -> list[ModelRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT m.model_id, m.provider_id, p.name, m.upstream_model, m.display_name, m.enabled, "
                "m.created_at, m.origin_gateway "
                "FROM models m JOIN providers p ON p.provider_id = m.provider_id ORDER BY m.created_at"
            ).fetchall()
        return [
            ModelRecord(
                model_id=r[0], provider_id=r[1], provider_name=r[2], upstream_model=r[3],
                display_name=r[4], enabled=bool(r[5]), created_at=r[6], origin_gateway=r[7],
            )
            for r in rows
        ]

    def delete_model(self, model_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM models WHERE model_id = ?", (model_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def resolve(self, model_id: str) -> Optional[ResolvedModel]:
        with self._lock:
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
            api_key = self.get_decrypted_key(provider_id)  # re-entrant lock
        return ResolvedModel(
            model_id=model_id, provider_id=provider_id, provider_name=provider_name, kind=kind,
            base_url=base_url, upstream_model=upstream_model, api_key=api_key,
        )

    def replace_registry(
        self, manager_gateway_id: str, providers: list[SyncProvider], models: list[SyncModel]
    ) -> None:
        """Manager-exclusive provider sync: atomically replace THIS instance's
        entire provider/model registry with the manager's set. Every row is
        stamped origin_gateway=manager_gateway_id. Plaintext api_keys are
        re-encrypted under this instance's own VaultCrypto here.

        Called ONLY with a validated manager response -- on a failed poll the
        caller leaves the existing registry untouched (last-known-good).
        """
        with self._lock:
            self._conn.execute("DELETE FROM models")
            self._conn.execute("DELETE FROM providers")
            for p in providers:
                nonce = ciphertext = sealed_dek = None
                key_last4 = None
                if p.api_key:
                    nonce, ciphertext, sealed_dek = self._crypto.encrypt(_AAD_NAMESPACE, p.provider_id, p.api_key)
                    key_last4 = p.api_key[-4:]
                self._conn.execute(
                    "INSERT INTO providers (provider_id, name, kind, base_url, api_key_nonce, "
                    "api_key_ciphertext, api_key_sealed_dek, key_last4, enabled, created_at, origin_gateway) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (p.provider_id, p.name, p.kind, p.base_url, nonce, ciphertext, sealed_dek,
                     key_last4, 1 if p.enabled else 0, p.created_at, manager_gateway_id),
                )
            for m in models:
                self._conn.execute(
                    "INSERT INTO models (model_id, provider_id, upstream_model, display_name, "
                    "enabled, created_at, origin_gateway) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (m.model_id, m.provider_id, m.upstream_model, m.display_name,
                     1 if m.enabled else 0, m.created_at, manager_gateway_id),
                )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
