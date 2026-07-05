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


def test_write_read_round_trip(tmp_path):
    store = _store(tmp_path)
    store.write_async("session-1", "tok1", "a@b.com")
    store.flush()
    assert store.get("session-1", "tok1") == "a@b.com"
    store.close()


def test_get_returns_none_for_unknown_token(tmp_path):
    store = _store(tmp_path)
    assert store.get("session-1", "does-not-exist") is None
    store.close()


def test_cache_serves_before_disk_write_lands(tmp_path):
    store = _store(tmp_path)
    store.write_async("session-1", "tok1", "a@b.com")
    # No flush() yet -- value must still be readable from the in-memory cache.
    assert store.get("session-1", "tok1") == "a@b.com"
    store.close()


def test_persists_across_new_store_instance_same_file(tmp_path):
    path = tmp_path / "vault.sqlite"
    crypto = VaultCrypto(_FakeRedis())
    store_a = SqliteVaultStore(crypto, storage_path=str(path))
    store_a.write_async("session-1", "tok1", "a@b.com")
    store_a.close()

    store_b = SqliteVaultStore(crypto, storage_path=str(path))
    assert store_b.get("session-1", "tok1") == "a@b.com"
    store_b.close()
