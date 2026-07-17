"""SqliteIngestDedupe: makes POST /v1/admin/audit/ingest idempotent.

A forwarding gateway (core/audit/sinks.py's ForwardingSink) removes a record
from its outbound queue only after a confirmed 2xx. If the manager commits a
record but the response is lost on the way back (timeout, dropped
connection), the sender legitimately retries -- so delivery is at-least-once
and the SAME record_id can arrive twice.

Without dedupe that means duplicate entries in a compliance audit log:
inflated counts, and a chain containing the same event twice. Worse, with
AUDIT_SINK=postgres the duplicate would violate the `record_id PRIMARY KEY`
in audit_records, raise, return 500, and the sender would retry that same
record forever -- a poison pill that blocks its whole ordered queue.

So the manager records every record_id it has appended and answers a repeat
with a plain 200 (already have it), letting the sender dequeue cleanly.
Persisted rather than in-memory so a manager restart doesn't reopen the
duplicate window.

Same construction shape as the other gateway SQLite stores (auth/store.py,
providers/registry_store.py): check_same_thread=False, CREATE TABLE IF NOT
EXISTS, plain sync methods, close().
"""
from __future__ import annotations

import sqlite3
import time

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ingested_records (
    record_id TEXT PRIMARY KEY,
    origin_gateway TEXT,
    ingested_at REAL NOT NULL
);
"""


class SqliteIngestDedupe:
    def __init__(self, storage_path: str = "./gateway_audit_ingest.sqlite") -> None:
        self._conn = sqlite3.connect(storage_path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def seen(self, record_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM ingested_records WHERE record_id = ?", (record_id,)
        ).fetchone()
        return row is not None

    def mark(self, record_id: str, origin_gateway: str | None) -> None:
        # INSERT OR IGNORE: marking an already-marked record is a no-op
        # rather than an error, so a racing retry can't 500.
        self._conn.execute(
            "INSERT OR IGNORE INTO ingested_records (record_id, origin_gateway, ingested_at) VALUES (?, ?, ?)",
            (record_id, origin_gateway, time.time()),
        )
        self._conn.commit()

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM ingested_records").fetchone()[0])

    def close(self) -> None:
        self._conn.close()
