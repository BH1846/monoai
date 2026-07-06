from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse

from audit.evidence import export, sign_evidence
from audit.sinks import JsonlSink, PostgresSink, UnsignedAuditRecordError, read_jsonl

router = APIRouter()


@router.get("/v1/evidence/export")
async def evidence_export(request: Request, path: str | None = Query(default=None)) -> Response:
    """Ed25519-signed hash-chained evidence bundle (G10). The
    `X-Evidence-Signature` / `X-Evidence-Public-Key` response headers let
    an auditor verify the bundle offline with only the public key --
    audit.evidence.verify_signature(bundle_bytes, signature, public_key)."""
    settings = request.app.state.settings
    audit_sink = request.app.state.audit_chain._sink
    require_signature = settings.audit_sign_enabled

    try:
        if path:
            records = read_jsonl(path, require_signature=require_signature)
        elif isinstance(audit_sink, PostgresSink):
            records = audit_sink.read_all(require_signature=require_signature)
        elif isinstance(audit_sink, JsonlSink):
            try:
                records = read_jsonl(settings.audit_log_path, require_signature=require_signature)
            except FileNotFoundError:
                records = []
        else:
            records = []
    except UnsignedAuditRecordError as err:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "type": "unsigned_audit_record",
                    "message": str(err),
                    "record_id": err.record_id,
                }
            },
        )

    bundle = export(records)
    sig = sign_evidence(bundle, request.app.state.signing_key)
    return Response(
        content=bundle,
        media_type="application/x-ndjson",
        headers={"X-Evidence-Signature": sig["signature"], "X-Evidence-Public-Key": sig["public_key"]},
    )
