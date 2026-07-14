"""File PII scanning endpoint. A user uploads a document/image; the gateway
extracts its text (OCR for images and scanned PDFs), runs the same
detect+policy pipeline the chat path uses, and returns the redacted text +
a findings report -- so PII in an attached file is stripped before it ever
reaches a model.

Takes JSON (base64 file bytes) rather than multipart so the web proxy can
forward it as-is; auth is the caller's own virtual key (the file is scanned
under that key's policy), same as /v1/chat/completions.
"""
from __future__ import annotations

import base64
from typing import Any

from auth.middleware import authenticate
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from filescan import OcrUnavailableError, UnsupportedFileTypeError, detect_kind, scan_file

router = APIRouter()


@router.post("/v1/files/scan")
async def scan_uploaded_file(
    request: Request,
    body: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> Any:
    key = authenticate(authorization, request.app.state.key_store)

    filename = body.get("filename") or "upload"
    content_type = body.get("content_type")
    data_b64 = body.get("data_base64")
    if not isinstance(data_b64, str) or not data_b64:
        return JSONResponse(status_code=400, content={"error": {"type": "invalid_request", "message": "'data_base64' is required"}})

    # Accept either a raw base64 string or a full data: URL.
    if data_b64.startswith("data:"):
        data_b64 = data_b64.split(",", 1)[-1]
    try:
        data = base64.b64decode(data_b64)
    except Exception:
        return JSONResponse(status_code=400, content={"error": {"type": "invalid_request", "message": "data_base64 is not valid base64"}})

    try:
        kind = detect_kind(filename, content_type)
    except UnsupportedFileTypeError as err:
        return JSONResponse(status_code=415, content={"error": {"type": "unsupported_file_type", "message": str(err)}})

    policy = request.app.state.policy_store.get(key.policy_id)
    pipeline = request.app.state.detection_pipeline

    try:
        result = scan_file(data, filename, kind, pipeline, policy)
    except OcrUnavailableError as err:
        return JSONResponse(status_code=503, content={"error": {"type": "ocr_unavailable", "message": str(err)}})
    except Exception as err:  # noqa: BLE001 -- surface extraction failures as 422, not a 500
        return JSONResponse(status_code=422, content={"error": {"type": "extraction_failed", "message": str(err)}})

    return {
        "filename": result.filename,
        "kind": result.kind,
        "policy_id": result.policy_id,
        "units_scanned": result.units_scanned,
        "blocked": result.blocked,
        "span_counts_by_label": result.span_counts_by_label,
        "redacted_text": result.redacted_text,
        "findings": [{"location": f.location, "label": f.label, "action": f.action} for f in result.findings],
    }
