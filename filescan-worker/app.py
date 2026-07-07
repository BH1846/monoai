"""filescan-worker: standalone FastAPI sub-service (G16, Phase 3) --
directly imports core/detect + core/policy to scan uploaded documents
(PDF/DOCX/XLSX/CSV) for PII/sensitive content, independent of the main
gateway's chat request path (no session/vault involvement -- see
scan.py's docstring).

Run standalone: uv run uvicorn app:app --app-dir filescan-worker --port 8001

POST /v1/files/scan          -- synchronous; returns the full scan report.
POST /v1/files/scan-async    -- 202 Accepted + `Location` header pointing
                                 at the polling endpoint below.
GET  /v1/files/scan-async/{job_id} -- poll: {"status": "processing"} until
                                 {"status": "done", "result": {...}} or
                                 {"status": "error", "error": "..."}.
"""
from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from detect.pipeline import DetectionPipeline
from fastapi import FastAPI, HTTPException, Response, UploadFile
from policy.store import PolicyStore

from extract import UnsupportedFileTypeError, detect_kind
from jobs import JobStore
from scan import scan_file

_REPO_ROOT = Path(__file__).resolve().parent.parent
_POLICY_DIR = os.environ.get("POLICY_DIR", str(_REPO_ROOT / "policies"))

app = FastAPI(title="monoai-filescan-worker")

_pipeline = DetectionPipeline()
_policy_store = PolicyStore()
_policy_store.load_dir(_POLICY_DIR)
_jobs = JobStore()


def _resolve_policy(policy_id: str) -> Any:
    try:
        return _policy_store.get(policy_id)
    except KeyError as err:
        raise HTTPException(status_code=400, detail=f"unknown policy_id: {policy_id!r}") from err


async def _read_and_classify(file: UploadFile) -> tuple[bytes, str, str]:
    data = await file.read()
    try:
        kind = detect_kind(file.filename, file.content_type)
    except UnsupportedFileTypeError as err:
        raise HTTPException(status_code=415, detail=str(err)) from err
    return data, file.filename or "upload", kind


@app.post("/v1/files/scan")
async def scan_sync(file: UploadFile, policy_id: str = "default") -> dict:
    data, filename, kind = await _read_and_classify(file)
    policy = _resolve_policy(policy_id)
    result = scan_file(data, filename, kind, _pipeline, policy)
    return asdict(result)


@app.post("/v1/files/scan-async", status_code=202)
async def scan_async(response: Response, file: UploadFile, policy_id: str = "default") -> dict:
    data, filename, kind = await _read_and_classify(file)
    policy = _resolve_policy(policy_id)

    job_id = _jobs.submit(lambda: asdict(scan_file(data, filename, kind, _pipeline, policy)))
    response.headers["Location"] = f"/v1/files/scan-async/{job_id}"
    return {"job_id": job_id, "status": "processing"}


@app.get("/v1/files/scan-async/{job_id}")
async def scan_async_status(job_id: str) -> dict:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown job_id")
    body: dict[str, Any] = {"job_id": job.job_id, "status": job.status}
    if job.status == "done":
        body["result"] = job.result
    elif job.status == "error":
        body["error"] = job.error
    return body


@app.get("/health/live")
async def health_live() -> dict:
    return {"status": "ok"}
