"""SqliteVaultStore: dev/single-node vault storage backend.

Ported from SENTINEL-2.0/pii_pipeline/vault.py's SQLite half (schema,
in-memory cache, ThreadPoolExecutor async-write pattern), now implementing
the VaultStore protocol and taking a VaultCrypto collaborator instead of
owning encryption inline.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor

from vault.crypto import VaultCrypto

_SCHEMA = """
CREATE TABLE IF NOT EXISTS vault_entries (
    session_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    nonce BLOB NOT NULL,
    ciphertext BLOB NOT NULL,
    sealed_dek BLOB NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (session_id, token_id)
)
"""


class SqliteVaultStore:
    def __init__(self, crypto: VaultCrypto, storage_path: str = "./pii_vault.sqlite") -> None:
        self._crypto = crypto
        self._conn = sqlite3.connect(storage_path, check_same_thread=False)
        self._conn.execute(_SCHEMA)
        self._conn.commit()
        self._lock = threading.Lock()
        self._cache: dict[tuple[str, str], str] = {}
        self._cache_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._pending: list[Future] = []

    def write_async(self, session_id: str, token_id: str, plaintext: str) -> None:
        with self._cache_lock:
            self._cache[(session_id, token_id)] = plaintext
        future = self._executor.submit(self._encrypt_and_store, session_id, token_id, plaintext)
        self._pending.append(future)

    def _encrypt_and_store(self, session_id: str, token_id: str, plaintext: str) -> None:
        nonce, ciphertext, sealed_dek = self._crypto.encrypt(session_id, token_id, plaintext)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO vault_entries "
                "(session_id, token_id, nonce, ciphertext, sealed_dek, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, token_id, nonce, ciphertext, sealed_dek, time.time()),
            )
            self._conn.commit()

    def get(self, session_id: str, token_id: str) -> str | None:
        with self._cache_lock:
            cached = self._cache.get((session_id, token_id))
        if cached is not None:
            return cached

        with self._lock:
            row = self._conn.execute(
                "SELECT nonce, ciphertext, sealed_dek FROM vault_entries "
                "WHERE session_id = ? AND token_id = ?",
                (session_id, token_id),
            ).fetchone()
        if row is None:
            return None
        nonce, ciphertext, sealed_dek = row
        plaintext = self._crypto.decrypt(session_id, token_id, nonce, ciphertext, sealed_dek)
        with self._cache_lock:
            self._cache[(session_id, token_id)] = plaintext
        return plaintext

    def flush(self, timeout: float | None = None) -> None:
        """Block until all pending async writes land. Test/eval use only."""
        for future in self._pending:
            future.result(timeout=timeout)
        self._pending.clear()

    def close(self) -> None:
        self.flush()
        self._executor.shutdown(wait=True)
        with self._lock:
            self._conn.close()
