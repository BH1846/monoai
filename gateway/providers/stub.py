"""Stub Provider Adapter — configurable failure injection for testing.
Ported verbatim from Lite_Multimodel_switching/monoai_router/providers/stub.py.
"""
from __future__ import annotations

import asyncio
import random
import time

from providers.base import ProviderAdapter
from router.contracts import ProviderResponse, RequestContext


class StubProviderError(RuntimeError):
    """Raised by StubProvider to simulate a provider failure."""


class StubProvider(ProviderAdapter):
    def __init__(
        self,
        provider_name: str = "stub",
        failure_rate: float = 0.0,
        latency_ms: float = 80.0,
        latency_jitter_ms: float = 20.0,
        models_always_fail: set[str] | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.failure_rate = failure_rate
        self.latency_ms = latency_ms
        self.latency_jitter_ms = latency_jitter_ms
        self.models_always_fail = models_always_fail or set()

    async def complete(self, request_id: str, model_id: str, ctx: RequestContext) -> ProviderResponse:
        t0 = time.monotonic()

        jitter = random.uniform(-self.latency_jitter_ms, self.latency_jitter_ms)
        sleep = max(0.0, (self.latency_ms + jitter) / 1000.0)
        await asyncio.sleep(sleep)

        if model_id in self.models_always_fail or random.random() < self.failure_rate:
            raise StubProviderError(f"injected failure: model={model_id}")

        latency_ms = (time.monotonic() - t0) * 1000.0
        last_msg = ctx.messages[-1] if ctx.messages else None
        last_text = (last_msg.content if isinstance(last_msg.content, str) else "") if last_msg else ""

        return ProviderResponse(
            request_id=request_id,
            model_id=model_id,
            provider=self.provider_name,
            content=f"[{model_id}] stub response to: {str(last_text)[:60]}",
            usage={"prompt_tokens": 20, "completion_tokens": 30, "total_tokens": 50},
            latency_ms=latency_ms,
        )
