"""SqliteVaultStore: dev/single-node vault storage backend.

Ported from SENTINEL-2.0/pii_pipeline/vault.py's SQLite half (schema,
in-memory cache, ThreadPoolExecutor async-write pattern), now implementing
the VaultStore protocol and taking a VaultCrypto collaborator instead of
owning encryption inline. TTL + erasure (G11) added on top: `expires_at`
column, `sweep_expired()`, `erase_session()`.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Optional

from vault.crypto import VaultCrypto

_SCHEMA = """
CREATE TABLE IF NOT EXISTS vault_entries (
    session_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    nonce BLOB NOT NULL,
    ciphertext BLOB NOT NULL,
    sealed_dek BLOB NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL,
    PRIMARY KEY (session_id, token_id)
)
"""


class SqliteVaultStore:
    def __init__(
        self, crypto: VaultCrypto, storage_path: str = "./pii_vault.sqlite", default_ttl_s: Optional[float] = None
    ) -> None:
        self._crypto = crypto
        self._default_ttl_s = default_ttl_s
        self._conn = sqlite3.connect(storage_path, check_same_thread=False)
        self._conn.execute(_SCHEMA)
        self._ensure_expires_at_column()
        self._conn.commit()
        self._lock = threading.Lock()
        self._cache: dict[tuple[str, str], str] = {}
        self._cache_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._pending: list[Future] = []

    def _ensure_expires_at_column(self) -> None:
        # Pre-existing dev databases from before G11 won't have this
        # column yet -- add it rather than requiring a manual migration.
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(vault_entries)").fetchall()}
        if "expires_at" not in cols:
            self._conn.execute("ALTER TABLE vault_entries ADD COLUMN expires_at REAL")

    def write_async(
        self, session_id: str, token_id: str, plaintext: str, ttl_s: Optional[float] = None
    ) -> None:
        with self._cache_lock:
            self._cache[(session_id, token_id)] = plaintext
        future = self._executor.submit(self._encrypt_and_store, session_id, token_id, plaintext, ttl_s)
        self._pending.append(future)

    def _encrypt_and_store(
        self, session_id: str, token_id: str, plaintext: str, ttl_s: Optional[float]
    ) -> None:
        nonce, ciphertext, sealed_dek = self._crypto.encrypt(session_id, token_id, plaintext)
        now = time.time()
        ttl = ttl_s if ttl_s is not None else self._default_ttl_s
        expires_at = now + ttl if ttl is not None else None
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO vault_entries "
                "(session_id, token_id, nonce, ciphertext, sealed_dek, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, token_id, nonce, ciphertext, sealed_dek, now, expires_at),
            )
            self._conn.commit()

    def get(self, session_id: str, token_id: str) -> Optional[str]:
        with self._cache_lock:
            cached = self._cache.get((session_id, token_id))
        if cached is not None:
            return cached

        with self._lock:
            row = self._conn.execute(
                "SELECT nonce, ciphertext, sealed_dek, expires_at FROM vault_entries "
                "WHERE session_id = ? AND token_id = ?",
                (session_id, token_id),
            ).fetchone()
        if row is None:
            return None
        nonce, ciphertext, sealed_dek, expires_at = row
        if expires_at is not None and expires_at < time.time():
            return None
        plaintext = self._crypto.decrypt(session_id, token_id, nonce, ciphertext, sealed_dek)
        with self._cache_lock:
            self._cache[(session_id, token_id)] = plaintext
        return plaintext

    def sweep_expired(self) -> int:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM vault_entries WHERE expires_at IS NOT NULL AND expires_at < ?",
                (time.time(),),
            )
            self._conn.commit()
            return cur.rowcount

    def erase_session(self, session_id: str) -> int:
        with self._cache_lock:
            for key in [k for k in self._cache if k[0] == session_id]:
                del self._cache[key]
        with self._lock:
            cur = self._conn.execute("DELETE FROM vault_entries WHERE session_id = ?", (session_id,))
            self._conn.commit()
            return cur.rowcount

    def flush(self, timeout: Optional[float] = None) -> None:
        """Block until all pending async writes land. Test/eval use only."""
        for future in self._pending:
            future.result(timeout=timeout)
        self._pending.clear()

    def close(self) -> None:
        self.flush()
        self._executor.shutdown(wait=True)
        with self._lock:
            self._conn.close()
