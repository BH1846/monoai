import pytest
from providers.registry_store import SqliteProviderStore
from vault.crypto import VaultCrypto


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


def _store(tmp_path) -> SqliteProviderStore:
    crypto = VaultCrypto(_FakeRedis())
    return SqliteProviderStore(crypto, storage_path=str(tmp_path / "providers.sqlite"))


def test_provider_key_encrypted_not_raw_on_disk(tmp_path):
    store = _store(tmp_path)
    record = store.add_provider(name="groq", kind="openai-compatible", base_url="https://api.groq.com/openai/v1", api_key="gsk_supersecret123")

    assert record.provider_id.startswith("prov_")
    assert record.key_last4 == "t123"

    db_bytes = (tmp_path / "providers.sqlite").read_bytes()
    assert b"gsk_supersecret123" not in db_bytes
    store.close()


def test_list_providers_never_leaks_full_key(tmp_path):
    store = _store(tmp_path)
    store.add_provider(name="groq", kind="openai-compatible", base_url="https://api.groq.com/openai/v1", api_key="gsk_supersecret123")

    listed = store.list_providers()
    assert len(listed) == 1
    assert listed[0].key_last4 == "t123"
    assert not hasattr(listed[0], "api_key")
    store.close()


def test_get_decrypted_key_round_trip(tmp_path):
    store = _store(tmp_path)
    record = store.add_provider(name="groq", kind="openai-compatible", base_url="https://api.groq.com/openai/v1", api_key="gsk_supersecret123")

    assert store.get_decrypted_key(record.provider_id) == "gsk_supersecret123"
    store.close()


def test_ollama_provider_without_api_key(tmp_path):
    store = _store(tmp_path)
    record = store.add_provider(name="local-ollama", kind="ollama", base_url="http://localhost:11434")

    assert record.key_last4 is None
    assert store.get_decrypted_key(record.provider_id) is None
    store.close()


def test_add_provider_rejects_unknown_kind(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.add_provider(name="x", kind="bogus", base_url="http://example.com")
    store.close()


def test_add_model_and_resolve(tmp_path):
    store = _store(tmp_path)
    provider = store.add_provider(name="groq", kind="openai-compatible", base_url="https://api.groq.com/openai/v1", api_key="gsk_key")
    store.add_model(model_id="demo-model", provider_id=provider.provider_id, upstream_model="llama-3.1-8b-instant")

    resolved = store.resolve("demo-model")
    assert resolved is not None
    assert resolved.provider_name == "groq"
    assert resolved.upstream_model == "llama-3.1-8b-instant"
    assert resolved.api_key == "gsk_key"
    store.close()


def test_resolve_returns_none_for_unknown_model(tmp_path):
    store = _store(tmp_path)
    assert store.resolve("does-not-exist") is None
    store.close()


def test_add_model_rejects_unknown_provider(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.add_model(model_id="demo-model", provider_id="prov_nonexistent")
    store.close()


def test_list_models_includes_provider_name(tmp_path):
    store = _store(tmp_path)
    provider = store.add_provider(name="groq", kind="openai-compatible", base_url="https://api.groq.com/openai/v1")
    store.add_model(model_id="demo-model", provider_id=provider.provider_id)

    models = store.list_models()
    assert len(models) == 1
    assert models[0].provider_name == "groq"
    assert models[0].upstream_model == "demo-model"
    store.close()


def test_delete_provider_and_model(tmp_path):
    store = _store(tmp_path)
    provider = store.add_provider(name="groq", kind="openai-compatible", base_url="https://api.groq.com/openai/v1")
    store.add_model(model_id="demo-model", provider_id=provider.provider_id)

    assert store.delete_model("demo-model") is True
    assert store.delete_model("demo-model") is False
    assert store.delete_provider(provider.provider_id) is True
    assert store.delete_provider(provider.provider_id) is False
    store.close()


def test_persists_across_new_store_instance_same_file(tmp_path):
    path = tmp_path / "providers.sqlite"
    crypto = VaultCrypto(_FakeRedis())
    store_a = SqliteProviderStore(crypto, storage_path=str(path))
    provider = store_a.add_provider(name="groq", kind="openai-compatible", base_url="https://api.groq.com/openai/v1", api_key="gsk_key")
    store_a.add_model(model_id="demo-model", provider_id=provider.provider_id)
    store_a.close()

    store_b = SqliteProviderStore(crypto, storage_path=str(path))
    resolved = store_b.resolve("demo-model")
    assert resolved is not None
    assert resolved.api_key == "gsk_key"
    store_b.close()
