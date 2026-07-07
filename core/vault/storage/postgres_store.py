"""PostgresVaultStore: multi-worker-safe production vault backend.

Sync (psycopg3, not asyncpg — see DECISIONS.md): mirrors
SqliteVaultStore's shape exactly (in-memory cache + ThreadPoolExecutor
fire-and-forget writes) so it's a drop-in swap behind the same
VaultStore protocol. Real, multi-worker-safe: two separate
PostgresVaultStore instances pointed at the same DSN (simulating two
gateway worker processes) share state through Postgres itself, not any
in-process cache -- see tests/integration/test_postgres_vault.py's
two-worker rehydration proof test.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Optional

from vault.crypto import VaultCrypto

_SCHEMA = """
CREATE TABLE IF NOT EXISTS vault_entries (
    session_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    nonce BYTEA NOT NULL,
    ciphertext BYTEA NOT NULL,
    sealed_dek BYTEA NOT NULL,
    created_at DOUBLE PRECISION NOT NULL,
    expires_at DOUBLE PRECISION,
    PRIMARY KEY (session_id, token_id)
)
"""


class PostgresVaultStore:
    def __init__(self, crypto: VaultCrypto, dsn: str, default_ttl_s: Optional[float] = None) -> None:
        import psycopg

        self._crypto = crypto
        self._default_ttl_s = default_ttl_s
        self._conn = psycopg.connect(dsn, autocommit=True)
        self._conn.execute(_SCHEMA)
        self._lock = threading.Lock()
        self._cache: dict[tuple[str, str], tuple[str, Optional[float]]] = {}
        self._cache_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._pending: list[Future] = []

    def write_async(
        self, session_id: str, token_id: str, plaintext: str, ttl_s: Optional[float] = None
    ) -> None:
        ttl = ttl_s if ttl_s is not None else self._default_ttl_s
        expires_at = time.time() + ttl if ttl is not None else None
        with self._cache_lock:
            self._cache[(session_id, token_id)] = (plaintext, expires_at)
        future = self._executor.submit(self._encrypt_and_store, session_id, token_id, plaintext, expires_at)
        self._pending.append(future)

    def _encrypt_and_store(
        self, session_id: str, token_id: str, plaintext: str, expires_at: Optional[float]
    ) -> None:
        nonce, ciphertext, sealed_dek = self._crypto.encrypt(session_id, token_id, plaintext)
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO vault_entries "
                "(session_id, token_id, nonce, ciphertext, sealed_dek, created_at, expires_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (session_id, token_id) DO UPDATE SET "
                "nonce = EXCLUDED.nonce, ciphertext = EXCLUDED.ciphertext, "
                "sealed_dek = EXCLUDED.sealed_dek, created_at = EXCLUDED.created_at, "
                "expires_at = EXCLUDED.expires_at",
                (session_id, token_id, nonce, ciphertext, sealed_dek, now, expires_at),
            )

    def get(self, session_id: str, token_id: str) -> Optional[str]:
        key = (session_id, token_id)
        with self._cache_lock:
            cached = self._cache.get(key)
        if cached is not None:
            plaintext, expires_at = cached
            if expires_at is None or expires_at >= time.time():
                return plaintext
            # Cached entry has expired since it was written -- evict it and
            # fall through to the DB read below (do NOT trust the cache on
            # a hit without re-checking expiry; this was the Phase 1 bug).
            with self._cache_lock:
                self._cache.pop(key, None)

        with self._lock:
            row = self._conn.execute(
                "SELECT nonce, ciphertext, sealed_dek, expires_at FROM vault_entries "
                "WHERE session_id = %s AND token_id = %s",
                (session_id, token_id),
            ).fetchone()
        if row is None:
            return None
        nonce, ciphertext, sealed_dek, expires_at = row
        if expires_at is not None and expires_at < time.time():
            return None
        plaintext = self._crypto.decrypt(
            session_id, token_id, bytes(nonce), bytes(ciphertext), bytes(sealed_dek)
        )
        with self._cache_lock:
            self._cache[key] = (plaintext, expires_at)
        return plaintext

    def sweep_expired(self) -> int:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM vault_entries WHERE expires_at IS NOT NULL AND expires_at < %s",
                (time.time(),),
            )
            return cur.rowcount

    def erase_session(self, session_id: str) -> int:
        with self._cache_lock:
            for key in [k for k in self._cache if k[0] == session_id]:
                del self._cache[key]
        with self._lock:
            cur = self._conn.execute("DELETE FROM vault_entries WHERE session_id = %s", (session_id,))
            return cur.rowcount

    def flush(self, timeout: Optional[float] = None) -> None:
        for future in self._pending:
            future.result(timeout=timeout)
        self._pending.clear()

    def close(self) -> None:
        self.flush()
        self._executor.shutdown(wait=True)
        with self._lock:
            self._conn.close()
