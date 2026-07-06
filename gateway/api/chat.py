"""POST /v1/chat/completions -- non-streaming first, then streaming.

Streaming note (see DECISIONS.md): Phase 1's streaming branch chunks the
already-fetched (but NOT yet output-scanned/rehydrated) provider response
into small artificial pieces and feeds them through
gateway/streaming.py's StreamRehydrator -- proving the sliding-window
mechanism end-to-end over the real request path. True token-by-token
upstream SSE proxying (the provider itself streaming) is a later
refinement; the rehydrator's correctness doesn't depend on where the
chunk boundaries come from.
"""
from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse

from auth.middleware import authenticate, check_budget, check_model_allowed, check_rate_limit
from orchestrator import ChatResult, Orchestrator, ProviderFailureError
from pii import BlockedContentError
from router.normalizer import NormalizationError
from streaming import StreamRehydrator

router = APIRouter()

_STREAM_CHUNK_SIZE = 4  # artificial upstream chunk granularity, see module docstring


def _blocked_response(err: BlockedContentError) -> JSONResponse:
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
    )


def _provider_failure_response(err: ProviderFailureError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": {"type": "provider_unavailable", "message": str(err), "tier": err.tier}},
    )


def _chat_response_body(result: ChatResult) -> dict[str, Any]:
    return {
        "id": result.request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": result.model_id,
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": result.content}, "finish_reason": "stop"}
        ],
        "usage": result.usage,
        "monoai": {
            "session_id": result.session_id,
            "provider": result.provider,
            "difficulty": result.difficulty,
            "cost_usd": result.cost_usd,
            "policy_id": result.policy_id,
            "policy_version": result.policy_version,
            "unresolved_tokens": result.unresolved_tokens,
            "review_required": result.review_required,
            "sanitized_prompt": result.sanitized_prompt,
            "raw_model_output": result.raw_model_output,
        },
    }


async def _artificial_upstream(text: str) -> AsyncIterator[str]:
    for i in range(0, len(text), _STREAM_CHUNK_SIZE):
        yield text[i:i + _STREAM_CHUNK_SIZE]


@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    authorization: str | None = Header(default=None),
) -> Any:
    settings = request.app.state.settings
    key_store = request.app.state.key_store
    limiter = request.app.state.rate_limiter
    orchestrator: Orchestrator = request.app.state.orchestrator

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": {"type": "invalid_request", "message": "invalid JSON body"}})

    model_id = payload.get("model")

    key = authenticate(authorization, key_store)
    check_budget(key)
    check_model_allowed(key, model_id)
    check_rate_limit(key, limiter)

    session_id = payload.get("session_id")
    stream = bool(payload.get("stream", False))

    if not stream:
        try:
            result = await orchestrator.chat(
                payload, policy_id=key.policy_id, virtual_key_id=key.key_id,
                team_id=key.team_id, session_id=session_id,
            )
        except BlockedContentError as err:
            return _blocked_response(err)
        except ProviderFailureError as err:
            return _provider_failure_response(err)
        except NormalizationError as err:
            return JSONResponse(status_code=400, content={"error": {"type": "invalid_request", "message": str(err)}})

        if key.budget_usd_monthly is not None and result.cost_usd:
            key_store.update_budget_spent(key.key_id, key.budget_usd_spent + result.cost_usd)

        return JSONResponse(status_code=200, content=_chat_response_body(result))

    try:
        prepared = await orchestrator.prepare_dispatch(
            payload, policy_id=key.policy_id, virtual_key_id=key.key_id,
            team_id=key.team_id, session_id=session_id,
        )
    except BlockedContentError as err:
        return _blocked_response(err)
    except ProviderFailureError as err:
        return _provider_failure_response(err)
    except NormalizationError as err:
        return JSONResponse(status_code=400, content={"error": {"type": "invalid_request", "message": str(err)}})

    rehydrator = StreamRehydrator(
        session_id=prepared.session_id,
        pii=request.app.state.pii,
        policy=prepared.policy,
        input_token_ids=prepared.sanitize_result.token_ids,
    )

    async def _sse() -> AsyncIterator[str]:
        t2 = time.monotonic()
        final_text_parts: list[str] = []
        async for piece in rehydrator.run(_artificial_upstream(prepared.fb_result.response.content)):
            final_text_parts.append(piece)
            yield f"data: {json.dumps({'choices': [{'delta': {'content': piece}}]})}\n\n"
        output_scan_and_rehydrate_ms = (time.monotonic() - t2) * 1000.0

        result = orchestrator.finalize_stream(
            prepared, "".join(final_text_parts), rehydrator.unresolved,
            rehydrator.review_required, output_scan_and_rehydrate_ms, 0.0,
            ttfb_ms=rehydrator.ttfb_ms,
        )
        if key.budget_usd_monthly is not None and result.cost_usd:
            key_store.update_budget_spent(key.key_id, key.budget_usd_spent + result.cost_usd)

        yield "data: [DONE]\n\n"

    return StreamingResponse(_sse(), media_type="text/event-stream")
