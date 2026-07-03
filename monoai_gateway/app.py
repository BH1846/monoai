"""FastAPI surface for the gateway.

    POST /v1/chat/completions   OpenAI-compatible chat endpoint
    GET  /health                liveness/readiness

Everything that isn't the reduced 9-step flow (see orchestrator.py) is out
of scope here -- see repo root README's "what's simplified" section. The
only auth implemented is a single optional bearer token via
MONOAI_BEARER_TOKEN; there is no RBAC, no per-key budget, no streaming.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from monoai_router.hot_path.normalizer import NormalizationError
from monoai_router.lite.dispatcher import MODEL_BY_DIFFICULTY
from monoai_router.lite.router import LiteRouter
from monoai_router.providers.base import ProviderAdapter
from monoai_router.providers.ollama_provider import OllamaProvider
from monoai_router.providers.stub import StubProvider

from .audit import AuditLogger
from .config import Settings, load_settings
from .orchestrator import BlockedContentError, Orchestrator
from .pii import PiiGuard
from .providers import CloudRoute, OpenAICompatibleProvider


def _build_provider(settings: Settings) -> ProviderAdapter:
    if settings.provider == "ollama":
        return OllamaProvider(base_url=settings.ollama_base_url)
    if settings.provider == "stub":
        return StubProvider()
    if settings.provider == "cloud":
        if not settings.cloud_api_base_url:
            raise ValueError("MONOAI_PROVIDER=cloud requires CLOUD_API_BASE_URL (see .env at the repo root)")

        # Router's difficulty tiers (see MODEL_BY_DIFFICULTY) -> whichever
        # real cloud model + API key you configured for that tier. Each
        # tier's own key wins over the shared CLOUD_API_KEY fallback, so
        # three separate per-model keys (e.g. OpenRouter) work as-is.
        tiers = {
            "simple": (settings.cloud_model_simple, settings.cloud_api_key_simple or settings.cloud_api_key),
            "moderate": (settings.cloud_model_moderate, settings.cloud_api_key_moderate or settings.cloud_api_key),
            "complex": (settings.cloud_model_complex, settings.cloud_api_key_complex or settings.cloud_api_key),
        }
        missing = [tier for tier, (model, key) in tiers.items() if not model or not key]
        if missing:
            raise ValueError(
                f"MONOAI_PROVIDER=cloud is missing model/key config for tier(s): {', '.join(missing)} "
                "(see .env at the repo root)"
            )

        routes = {
            MODEL_BY_DIFFICULTY[tier]: CloudRoute(model=model, api_key=key)
            for tier, (model, key) in tiers.items()
        }
        return OpenAICompatibleProvider(
            base_url=settings.cloud_api_base_url,
            routes=routes,
            provider_name=settings.cloud_provider_name,
        )
    raise ValueError(f"unknown MONOAI_PROVIDER: {settings.provider!r} (expected 'stub', 'ollama', or 'cloud')")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    pii = PiiGuard(vault_storage_path=settings.vault_storage_path, use_onnx_ner=settings.pii_use_onnx_ner)
    provider = _build_provider(settings)
    router = LiteRouter(provider, log_path=settings.router_log_path)
    audit = AuditLogger(path=settings.audit_log_path)

    app.state.settings = settings
    app.state.orchestrator = Orchestrator(pii, router, audit)
    app.state.audit = audit

    yield

    await pii.close()
    if isinstance(provider, (OllamaProvider, OpenAICompatibleProvider)):
        await provider.aclose()


app = FastAPI(title="monoai-gateway", lifespan=lifespan)


def _check_auth(authorization: str | None, settings: Settings) -> None:
    if not settings.bearer_token:
        return
    expected = f"Bearer {settings.bearer_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="missing or invalid bearer token")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok"}


@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    settings: Settings = request.app.state.settings
    _check_auth(authorization, settings)

    payload = await request.json()

    orchestrator: Orchestrator = request.app.state.orchestrator
    audit: AuditLogger = request.app.state.audit

    try:
        result = await orchestrator.chat(payload)
    except BlockedContentError as err:
        background_tasks.add_task(audit.write, err.audit_record)
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "type": "blocked_content",
                    "message": (
                        "Request rejected: prompt contains content classified BLOCK "
                        f"({', '.join(err.labels)}). This content is never sent to a model."
                    ),
                    "session_id": err.session_id,
                    "labels": err.labels,
                }
            },
            background=background_tasks,
        )
    except NormalizationError as err:
        return JSONResponse(status_code=400, content={"error": {"type": "invalid_request", "message": str(err)}})

    background_tasks.add_task(audit.write, result.audit_record)

    body = {
        "id": result.request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": result.model_id,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": result.content},
                "finish_reason": "stop",
            }
        ],
        "usage": result.usage,
        "monoai": {
            "session_id": result.session_id,
            "provider": result.provider,
            "difficulty": result.difficulty,
            "unresolved_tokens": result.unresolved_tokens,
            "review_required": result.review_required,
            "sanitized_prompt": result.sanitized_prompt,
            "raw_model_output": result.raw_model_output,
        },
    }
    return JSONResponse(status_code=200, content=body, background=background_tasks)
