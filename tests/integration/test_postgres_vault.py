"""G11 proof test: PostgresVaultStore two-worker rehydration (sanitize in
worker A, rehydrate in worker B -- proves state lives in Postgres, not
any in-process cache). Skips gracefully without a live Postgres.
"""
import os
import uuid

import pytest

DSN = os.environ.get("TEST_POSTGRES_DSN", "postgresql://monoai:monoai@127.0.0.1:5433/monoai")


def _postgres_available() -> bool:
    try:
        import psycopg

        with psycopg.connect(DSN, connect_timeout=2):
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _postgres_available(), reason="no live Postgres at TEST_POSTGRES_DSN")


class _FakeRedis:
    """Shared "Valkey" so both workers derive the SAME vault master key --
    in production this would be the real shared Valkey instance."""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def get(self, key: str):
        return self._store.get(key)

    def set(self, key: str, value: bytes, nx: bool = False):
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True


def test_postgres_backend_two_workers_rehydrate():
    from vault.crypto import VaultCrypto
    from vault.storage.postgres_store import PostgresVaultStore

    shared_redis = _FakeRedis()
    session_id = f"session-{uuid.uuid4().hex[:8]}"

    # Worker A: sanitize (write).
    crypto_a = VaultCrypto(shared_redis, key_name="test:pg:master_key")
    worker_a = PostgresVaultStore(crypto_a, DSN)
    worker_a.write_async(session_id, "tok1", "a@b.com")
    worker_a.flush()

    # Worker B: a SEPARATE process/instance, same DSN + same Valkey-backed
    # master key -- must be able to rehydrate what worker A wrote.
    crypto_b = VaultCrypto(shared_redis, key_name="test:pg:master_key")
    worker_b = PostgresVaultStore(crypto_b, DSN)
    try:
        assert worker_b.get(session_id, "tok1") == "a@b.com"
    finally:
        worker_a.erase_session(session_id)
        worker_a.close()
        worker_b.close()
