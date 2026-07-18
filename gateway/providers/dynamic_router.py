"""Resolves an explicit client-supplied `model` against the runtime
provider/model registry (providers/registry_store.py) into a dispatchable
Route, bypassing the difficulty-tier FallbackChain entirely -- see the
seam in orchestrator.py's prepare_dispatch(). Caches one ProviderAdapter
instance per provider_id so OpenAICompatibleProvider's per-key httpx
client cache (and OllamaProvider's single client) is reused across
requests instead of rebuilt on every call.
"""
from __future__ import annotations

from providers.fallback_chain import Route
from providers.ollama import OllamaProvider
from providers.openai_compatible import CloudRoute, OpenAICompatibleProvider
from providers.registry_store import SqliteProviderStore


class DynamicProviderRouter:
    def __init__(self, store: SqliteProviderStore) -> None:
        self._store = store
        self._adapters: dict[str, OllamaProvider | OpenAICompatibleProvider] = {}

    def resolve_route(self, model_id: str | None) -> Route | None:
        if not model_id or model_id == "auto":
            return None
        resolved = self._store.resolve(model_id)
        if resolved is None:
            return None

        if resolved.kind == "ollama":
            adapter = self._adapters.get(resolved.provider_id)
            if adapter is None:
                adapter = OllamaProvider(base_url=resolved.base_url)
                self._adapters[resolved.provider_id] = adapter
            return Route(provider=adapter, model_id=resolved.upstream_model, provider_name=resolved.provider_name)

        adapter = self._adapters.get(resolved.provider_id)
        if adapter is None:
            adapter = OpenAICompatibleProvider(base_url=resolved.base_url, routes={}, provider_name=resolved.provider_name)
            self._adapters[resolved.provider_id] = adapter
        adapter.set_route(resolved.upstream_model, CloudRoute(model=resolved.upstream_model, api_key=resolved.api_key or ""))
        return Route(provider=adapter, model_id=resolved.upstream_model, provider_name=resolved.provider_name)

    def invalidate(self) -> None:
        """Drop all cached ProviderAdapters. Called after a provider-sync
        reconcile so a synced provider whose base_url/key changed can't keep
        being served from a stale cached adapter. The adapters are rebuilt
        lazily on the next resolve_route(); the only cost is briefly losing
        httpx-client reuse, which is fine on an infrequent config change.

        NOTE: the old adapters' httpx clients are dropped without aclose()
        (this is a sync method called from the sync thread). They are GC'd;
        for the small provider counts here that's acceptable, and aclose()
        on the full set still runs at shutdown via the fresh cache.
        """
        self._adapters = {}

    async def aclose(self) -> None:
        for adapter in self._adapters.values():
            await adapter.aclose()
