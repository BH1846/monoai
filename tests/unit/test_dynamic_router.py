from providers.dynamic_router import DynamicProviderRouter
from providers.ollama import OllamaProvider
from providers.openai_compatible import OpenAICompatibleProvider
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


def test_resolve_route_returns_none_for_auto_and_missing_model(tmp_path):
    store = _store(tmp_path)
    router = DynamicProviderRouter(store)

    assert router.resolve_route(None) is None
    assert router.resolve_route("auto") is None
    assert router.resolve_route("unregistered-model") is None
    store.close()


def test_resolve_route_builds_openai_compatible_route(tmp_path):
    store = _store(tmp_path)
    provider = store.add_provider(name="groq", kind="openai-compatible", base_url="https://api.groq.com/openai/v1", api_key="gsk_key")
    store.add_model(model_id="demo-model", provider_id=provider.provider_id, upstream_model="llama-3.1-8b-instant")

    router = DynamicProviderRouter(store)
    route = router.resolve_route("demo-model")

    assert route is not None
    assert route.model_id == "llama-3.1-8b-instant"
    assert route.provider_name == "groq"
    assert isinstance(route.provider, OpenAICompatibleProvider)
    store.close()


def test_resolve_route_builds_ollama_route(tmp_path):
    store = _store(tmp_path)
    provider = store.add_provider(name="local-ollama", kind="ollama", base_url="http://localhost:11434")
    store.add_model(model_id="demo-model", provider_id=provider.provider_id, upstream_model="qwen2.5:7b")

    router = DynamicProviderRouter(store)
    route = router.resolve_route("demo-model")

    assert route is not None
    assert route.model_id == "qwen2.5:7b"
    assert isinstance(route.provider, OllamaProvider)
    store.close()


def test_resolve_route_reuses_cached_adapter_per_provider(tmp_path):
    store = _store(tmp_path)
    provider = store.add_provider(name="groq", kind="openai-compatible", base_url="https://api.groq.com/openai/v1", api_key="gsk_key")
    store.add_model(model_id="model-a", provider_id=provider.provider_id, upstream_model="llama-a")
    store.add_model(model_id="model-b", provider_id=provider.provider_id, upstream_model="llama-b")

    router = DynamicProviderRouter(store)
    route_a = router.resolve_route("model-a")
    route_b = router.resolve_route("model-b")

    assert route_a.provider is route_b.provider
    store.close()
