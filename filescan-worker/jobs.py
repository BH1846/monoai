"""In-memory async job tracking for POST /v1/files/scan-async (G16).

A single-process job store -- fine for an "embedded sub-service" per
the Phase 3 brief; a multi-worker production deployment would move
this to Valkey/Postgres, the same SQLite-first-then-Postgres tradeoff
core/vault already documents for Phase 1 (see DECISIONS.md). Flagged
here so it isn't forgotten, not implemented this phase.
"""
from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Literal, Optional

JobStatus = Literal["processing", "done", "error"]


@dataclass
class Job:
    job_id: str
    status: JobStatus = "processing"
    result: Any = None
    error: Optional[str] = None


class JobStore:
    def __init__(self, max_workers: int = 4) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        # Extraction (pypdf/docx/openpyxl parsing) and core/detect's NER
        # stage are both CPU-bound, synchronous work -- a thread pool,
        # not an asyncio task, keeps a scan-async request's FastAPI
        # event loop responsive to other requests while it runs.
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def submit(self, fn: Callable[[], Any]) -> str:
        job_id = uuid.uuid4().hex
        with self._lock:
            self._jobs[job_id] = Job(job_id=job_id)

        def _run() -> None:
            try:
                result = fn()
            except Exception as exc:  # noqa: BLE001 -- reported via job status, not raised
                with self._lock:
                    self._jobs[job_id].status = "error"
                    self._jobs[job_id].error = str(exc)
                return
            with self._lock:
                self._jobs[job_id].status = "done"
                self._jobs[job_id].result = result

        self._executor.submit(_run)
        return job_id

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)
