"""G11 proof tests: TTL expiry + right-to-erasure API, against
SqliteVaultStore (backend-agnostic behavior -- PostgresVaultStore
implements the identical contract, exercised live in
tests/integration/test_postgres_vault.py when Postgres is available).
"""
import time

from vault.crypto import VaultCrypto
from vault.storage.sqlite_store import SqliteVaultStore


class _FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def get(self, key: str):
        return self._store.get(key)

    def set(self, key: str, value: bytes, nx: bool = False):
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True


def _store(tmp_path) -> SqliteVaultStore:
    crypto = VaultCrypto(_FakeRedis())
    return SqliteVaultStore(crypto, storage_path=str(tmp_path / "vault.sqlite"))


def test_ttl_expiry(tmp_path):
    store = _store(tmp_path)
    store.write_async("session-1", "tok1", "a@b.com", ttl_s=0.05)
    store.flush()
    assert store.get("session-1", "tok1") == "a@b.com"

    time.sleep(0.1)
    assert store.get("session-1", "tok1") is None  # expired, not physically swept yet

    swept = store.sweep_expired()
    assert swept == 1
    store.close()


def test_entries_without_ttl_never_expire(tmp_path):
    store = _store(tmp_path)
    store.write_async("session-1", "tok1", "a@b.com")  # no ttl_s
    store.flush()
    time.sleep(0.05)
    assert store.get("session-1", "tok1") == "a@b.com"
    assert store.sweep_expired() == 0
    store.close()


def test_erasure_api_removes_value(tmp_path):
    store = _store(tmp_path)
    store.write_async("session-1", "tok1", "a@b.com")
    store.write_async("session-1", "tok2", "555-123-4567")
    store.write_async("session-2", "tok3", "other@example.com")
    store.flush()

    removed = store.erase_session("session-1")
    assert removed == 2
    assert store.get("session-1", "tok1") is None
    assert store.get("session-1", "tok2") is None
    assert store.get("session-2", "tok3") == "other@example.com"  # untouched
    store.close()
