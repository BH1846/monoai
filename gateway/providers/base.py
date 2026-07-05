"""Provider Adapter interface. The Dispatcher/fallback chain calls
complete() and expects a ProviderResponse on success, any exception on
failure (timeout, 4xx, 5xx, network error) -- retry/fallback decisions
live in gateway/providers/fallback_chain.py, not here.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from router.contracts import ProviderResponse, RequestContext


class ProviderAdapter(ABC):
    @abstractmethod
    async def complete(self, request_id: str, model_id: str, ctx: RequestContext) -> ProviderResponse:
        ...
