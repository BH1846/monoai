import pytest
from vault.crypto import VaultCrypto


class _FakeRedis:
    """Minimal in-memory stand-in for the Valkey client's .get()/.set(nx=)
    surface, so these unit tests don't need a live Valkey instance."""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def get(self, key: str):
        return self._store.get(key)

    def set(self, key: str, value: bytes, nx: bool = False):
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True


def test_encrypt_decrypt_round_trip():
    crypto = VaultCrypto(_FakeRedis())
    nonce, ciphertext, sealed_dek = crypto.encrypt("session-1", "tok1", "a@b.com")
    plaintext = crypto.decrypt("session-1", "tok1", nonce, ciphertext, sealed_dek)
    assert plaintext == "a@b.com"


def test_wrong_session_id_fails_to_decrypt():
    crypto = VaultCrypto(_FakeRedis())
    nonce, ciphertext, sealed_dek = crypto.encrypt("session-1", "tok1", "a@b.com")
    with pytest.raises(Exception):
        crypto.decrypt("session-WRONG", "tok1", nonce, ciphertext, sealed_dek)


def test_wrong_token_id_fails_to_decrypt():
    crypto = VaultCrypto(_FakeRedis())
    nonce, ciphertext, sealed_dek = crypto.encrypt("session-1", "tok1", "a@b.com")
    with pytest.raises(Exception):
        crypto.decrypt("session-1", "tok-WRONG", nonce, ciphertext, sealed_dek)


def test_master_key_persists_across_instances_against_same_client():
    redis = _FakeRedis()
    crypto_a = VaultCrypto(redis, key_name="test:key")
    crypto_b = VaultCrypto(redis, key_name="test:key")
    # Entry encrypted by A must be decryptable by B (same underlying keypair).
    nonce, ciphertext, sealed_dek = crypto_a.encrypt("s1", "t1", "secret-value")
    assert crypto_b.decrypt("s1", "t1", nonce, ciphertext, sealed_dek) == "secret-value"


def test_master_key_not_regenerated_if_already_present():
    redis = _FakeRedis()
    crypto_a = VaultCrypto(redis, key_name="test:key")
    existing_key_bytes = redis.get("test:key")
    VaultCrypto(redis, key_name="test:key")
    assert redis.get("test:key") == existing_key_bytes
