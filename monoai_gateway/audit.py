"""Append-only JSONL audit log.

One line per request: request_id, session_id, event (completed/blocked),
difficulty, model_id, provider, span counts by label, redacted count,
latencies, unresolved tokens. `write()` is a plain synchronous file append
-- callers that want it off the response path (see app.py) should invoke it
from a FastAPI BackgroundTask, which runs after the HTTP response is sent.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class AuditLogger:
    def __init__(self, path: str = "./gateway_audit.jsonl"):
        self._path = Path(path)

    def write(self, record: dict[str, Any]) -> None:
        record.setdefault("ts", time.time())
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
