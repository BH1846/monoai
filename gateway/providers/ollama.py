"""Real Ollama provider adapter -- local inference, no API key. Ported
verbatim from Lite_Multimodel_switching/monoai_router/providers/ollama_provider.py.
"""
from __future__ import annotations

import time
from typing import Any

import httpx
from router.contracts import ProviderResponse, RequestContext

from providers.base import ProviderAdapter


class OllamaProvider(ProviderAdapter):
    def __init__(self, base_url: str = "http://localhost:11434", timeout: float = 120.0) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def complete(self, request_id: str, model_id: str, ctx: RequestContext) -> ProviderResponse:
        t0 = time.monotonic()

        payload: dict[str, Any] = {
            "model": model_id,
            "messages": self._build_messages(ctx),
            "stream": False,
        }
        options: dict[str, Any] = {}
        if ctx.max_tokens is not None:
            options["num_predict"] = ctx.max_tokens
        if ctx.temperature is not None:
            options["temperature"] = ctx.temperature
        if options:
            payload["options"] = options
        if ctx.tools:
            payload["tools"] = ctx.tools

        response = await self._client.post("/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()

        latency_ms = (time.monotonic() - t0) * 1000.0
        content = data.get("message", {}).get("content") or ""

        prompt_tokens = data.get("prompt_eval_count", 0)
        completion_tokens = data.get("eval_count", 0)

        return ProviderResponse(
            request_id=request_id,
            model_id=model_id,
            provider="ollama",
            content=content,
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            latency_ms=latency_ms,
        )

    def _build_messages(self, ctx: RequestContext) -> list[dict[str, Any]]:
        result = []
        for msg in ctx.messages:
            if isinstance(msg.content, str):
                result.append({"role": msg.role, "content": msg.content})
                continue

            text_parts: list[str] = []
            images: list[str] = []
            for part in msg.content:
                if part.type == "text" and part.text:
                    text_parts.append(part.text)
                elif part.type == "image_base64" and part.image_data:
                    images.append(part.image_data)

            entry: dict[str, Any] = {"role": msg.role, "content": "\n".join(text_parts)}
            if images:
                entry["images"] = images
            result.append(entry)
        return result

    async def aclose(self) -> None:
        await self._client.aclose()
