from __future__ import annotations

from fastapi import APIRouter, Response

from obs.metrics import render

router = APIRouter()


@router.get("/metrics")
async def metrics() -> Response:
    return Response(content=render(), media_type="text/plain; version=0.0.4")
