from __future__ import annotations

from audit.evidence import export
from audit.sinks import read_jsonl
from fastapi import APIRouter, Query, Request, Response

router = APIRouter()


@router.get("/v1/evidence/export")
async def evidence_export(request: Request, path: str | None = Query(default=None)) -> Response:
    """Unsigned hash-chained evidence bundle (Ed25519 signing is Phase 2 —
    see DECISIONS.md). Anyone can independently recompute the chain and
    confirm it verifies."""
    settings = request.app.state.settings
    audit_path = path or settings.audit_log_path
    try:
        records = read_jsonl(audit_path)
    except FileNotFoundError:
        records = []
    bundle = export(records)
    return Response(content=bundle, media_type="application/x-ndjson")
