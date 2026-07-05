"""Generic OpenAI-compatible cloud provider adapter.

Works with any API that speaks the OpenAI chat-completions wire format --
Groq, OpenAI itself, OpenRouter, Together AI, Fireworks, etc. This is
gateway-side glue, not part of monoai_router (which only ships
Stub/Ollama/Groq-specific adapters): point it at any such endpoint by
setting base_url + a per-difficulty-tier (model, api_key) route table in
.env, without needing a new adapter class per vendor.

monoai_router's LiteDispatcher hardcodes Ollama-style model tags per
difficulty tier (llama3.2:3b / llama3.1:8b / qwen2.5:14b -- see
monoai_router/lite/dispatcher.py MODEL_BY_DIFFICULTY). That mapping is
internal to the router repo and out of scope to rewrite. Those tags aren't
real model IDs for a cloud vendor, so this adapter remaps them to whatever
you configured per tier, at the provider boundary -- the
normalizer/classifier/dispatcher are untouched.

Each tier can carry its own API key (e.g. three separate per-model
OpenRouter keys), not just one shared key -- httpx clients are created
lazily, one per distinct key, and reused across requests.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from monoai_router.contracts import ProviderResponse, RequestContext
from monoai_router.providers.base import ProviderAdapter


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
        # ProviderResponse.usage (monoai_router/contracts.py) is typed
        # dict[str, int] and belongs to the untouched submodule -- OpenRouter's
        # real per-request $ cost doesn't fit there, so it's kept here instead
        # and pulled out by request_id via pop_cost().
        self._last_cost: dict[str, float] = {}

    def pop_cost(self, request_id: str) -> float | None:
        return self._last_cost.pop(request_id, None)

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

    async def complete(
        self,
        request_id: str,
        model_id: str,
        ctx: RequestContext,
    ) -> ProviderResponse:
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
