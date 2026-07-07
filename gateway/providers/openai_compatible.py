"""Generic OpenAI-compatible cloud provider adapter -- works with any API
that speaks the OpenAI chat-completions wire format (Groq, OpenAI itself,
OpenRouter, Together AI, Fireworks, etc). Ported from
monoai_gateway/providers.py, keeping the request_id-keyed cost-extraction
fix found and applied during this rewrite's earlier session (pop_cost is
keyed by the SAME request_id the provider itself received, not some other
id generated upstream -- see test_openai_compatible_cost_extraction.py).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
from router.contracts import ProviderResponse, RequestContext

from providers.base import ProviderAdapter


@dataclass(frozen=True)
class CloudRoute:
    model: str
    api_key: str


class OpenAICompatibleProvider(ProviderAdapter):
    def __init__(
        self,
        base_url: str,
        routes: dict[str, CloudRoute],
        provider_name: str = "cloud",
        timeout: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._routes = routes
        self._provider_name = provider_name
        self._timeout = timeout
        self._clients: dict[str, httpx.AsyncClient] = {}
        # ProviderResponse.usage is typed dict[str,int]; a real $ cost
        # (float, e.g. OpenRouter's usage.cost) doesn't fit there, so it's
        # kept out-of-band here and pulled by request_id via pop_cost().
        self._last_cost: dict[str, float] = {}

    def pop_cost(self, request_id: str) -> float | None:
        return self._last_cost.pop(request_id, None)

    def set_route(self, key: str, route: CloudRoute) -> None:
        """Register/replace a route entry after construction -- used by the
        dynamic provider registry (providers/dynamic_router.py) to add
        admin-registered models to an already-running adapter instance
        without rebuilding its cached httpx clients."""
        self._routes[key] = route

    def _client_for(self, api_key: str) -> httpx.AsyncClient:
        client = self._clients.get(api_key)
        if client is None:
            client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=self._timeout,
            )
            self._clients[api_key] = client
        return client

    async def complete(self, request_id: str, model_id: str, ctx: RequestContext) -> ProviderResponse:
        t0 = time.monotonic()
        route = self._routes.get(model_id)
        if route is None:
            raise ValueError(
                f"no cloud route configured for router tier {model_id!r} -- "
                "set CLOUD_MODEL_*/CLOUD_API_KEY_* in .env"
            )

        client = self._client_for(route.api_key)
        payload: dict[str, Any] = {"model": route.model, "messages": self._build_messages(ctx)}
        if ctx.max_tokens is not None:
            payload["max_tokens"] = ctx.max_tokens
        if ctx.temperature is not None:
            payload["temperature"] = ctx.temperature

        response = await client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        latency_ms = (time.monotonic() - t0) * 1000.0
        choice = data["choices"][0]
        content = choice["message"].get("content") or ""
        usage = data.get("usage", {}) or {}
        if "cost" in usage:
            self._last_cost[request_id] = float(usage["cost"])

        return ProviderResponse(
            request_id=request_id,
            model_id=route.model,
            provider=self._provider_name,
            content=content,
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            latency_ms=latency_ms,
        )

    def _build_messages(self, ctx: RequestContext) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for msg in ctx.messages:
            if isinstance(msg.content, str):
                result.append({"role": msg.role, "content": msg.content})
                continue
            parts: list[dict[str, Any]] = []
            for part in msg.content:
                if part.type == "text" and part.text:
                    parts.append({"type": "text", "text": part.text})
                elif part.type == "image_url" and part.image_url:
                    parts.append({"type": "image_url", "image_url": {"url": part.image_url}})
                elif part.type == "image_base64" and part.image_data:
                    parts.append(
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{part.image_data}"}}
                    )
            result.append({"role": msg.role, "content": parts})
        return result

    async def aclose(self) -> None:
        for client in self._clients.values():
            await client.aclose()
