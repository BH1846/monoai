"""Durable, order-preserving outbound queue for audit forwarding.

Backs ForwardingSink (core/audit/sinks.py): when a gateway instance forwards
its audit records to a peer "manager" gateway, every record lands here first
and is removed ONLY after the manager confirms a 2xx. If the manager is
down -- or this gateway restarts -- nothing is lost and nothing is delivered
out of order.

Same construction shape as the other SQLite stores in this codebase
(gateway/auth/store.py, gateway/providers/registry_store.py): a
check_same_thread=False connection, CREATE TABLE IF NOT EXISTS, plain
synchronous methods, close(). check_same_thread=False matters here
specifically: append() is called on the gateway's request thread while the
drain runs on ForwardingSink's background thread.

Order is `seq INTEGER PRIMARY KEY AUTOINCREMENT` -- monotonic, and it
survives process restarts, so replay order == the order AuditChain.append()
produced the records in. Rows hold the already-serialized AuditRecord JSON;
the queue itself is deliberately payload-agnostic.
"""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS forward_queue (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""


@dataclass
class QueuedRecord:
    seq: int
    record_id: str
    payload_json: str


class SqliteForwardQueue:
    def __init__(self, storage_path: str) -> None:
        parent = Path(storage_path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(storage_path, check_same_thread=False)
        # WAL: a crash mid-write must not lose already-committed records.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        # sqlite3 connections are not safe to use concurrently even with
        # check_same_thread=False; the request thread (append) and the
        # forwarder thread (peek/ack) both touch this one.
        self._lock = threading.Lock()

    def append(self, record_id: str, payload_json: str, created_at: float) -> int:
        """Enqueue one serialized record. Returns its seq. Called on the
        gateway's request path -- a single local INSERT, no network I/O."""
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO forward_queue (record_id, payload_json, created_at) VALUES (?, ?, ?)",
                (record_id, payload_json, created_at),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def peek_batch(self, limit: int) -> list[QueuedRecord]:
        """Read (do NOT remove) the oldest `limit` records, in production
        order. The caller removes them via `ack` only after the manager
        confirms receipt, so a failed delivery never drops a record."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, record_id, payload_json FROM forward_queue ORDER BY seq ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [QueuedRecord(seq=r[0], record_id=r[1], payload_json=r[2]) for r in rows]

    def ack(self, seqs: list[int]) -> int:
        """Delete records the manager has durably accepted (2xx). Returns
        rows removed. Idempotent."""
        if not seqs:
            return 0
        placeholders = ",".join("?" for _ in seqs)
        with self._lock:
            removed = self._conn.execute(
                f"DELETE FROM forward_queue WHERE seq IN ({placeholders})", seqs
            ).rowcount
            self._conn.commit()
        return removed

    def pending_count(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM forward_queue").fetchone()[0])

    def close(self) -> None:
        with self._lock:
            self._conn.close()
