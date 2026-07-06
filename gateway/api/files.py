"""File/media scanning endpoints — Phase 3 (closes G16). Not wired into
gateway/app.py in Phase 1; see filescan-worker/README.md.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/v1/files/scan")
async def scan_file() -> None:
    raise HTTPException(status_code=501, detail="file scanning is Phase 3 — see filescan-worker/README.md")
