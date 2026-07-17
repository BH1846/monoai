"""Agent-side offline event buffer: a durable, append-only SQLite queue.

This is what makes the agent survive the manager being unreachable. Every
SENTINEL detection event the agent produces is appended here first; a
separate sync step drains it to the manager's /ingest IN ORDER and only
deletes rows the manager has durably accepted. If the manager is down, rows
accumulate; on reconnect they replay oldest-first.

Modeled on core/vault/storage/sqlite_store.py's shape (check_same_thread=
False connection, CREATE TABLE IF NOT EXISTS, plain sync methods, close()),
but it is a DIFFERENT domain -- an ordered outbound queue, not an encrypted
KV store -- so it is a new implementation rather than a reuse of vault code.

Ordering is by INTEGER PRIMARY KEY AUTOINCREMENT (`seq`), which is monotonic
and survives process restarts, so replay order == production order even
across crashes. Rows carry the already-serialized AgentEventPayload JSON;
the buffer is deliberately payload-agnostic.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS event_buffer (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""


@dataclass
class BufferedEvent:
    seq: int
    payload_json: str


class EventBuffer:
    def __init__(self, storage_path: str) -> None:
        Path(storage_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(storage_path, check_same_thread=False)
        # WAL: a crash mid-write must not lose already-committed events.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def append(self, payload_json: str, created_at: float) -> int:
        """Append one serialized event. Returns its seq. Called on the
        detection path -- fast, single INSERT."""
        cur = self._conn.execute(
            "INSERT INTO event_buffer (payload_json, created_at) VALUES (?, ?)",
            (payload_json, created_at),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def peek_batch(self, limit: int) -> list[BufferedEvent]:
        """Read (do NOT remove) the oldest `limit` pending events, in
        production order. The caller deletes them via `ack` only AFTER the
        manager confirms receipt -- so a failed/partial sync never drops
        events."""
        rows = self._conn.execute(
            "SELECT seq, payload_json FROM event_buffer ORDER BY seq ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [BufferedEvent(seq=r[0], payload_json=r[1]) for r in rows]

    def ack(self, seqs: list[int]) -> int:
        """Delete events the manager has durably accepted. Returns rows
        removed. Idempotent: acking an already-gone seq is a no-op."""
        if not seqs:
            return 0
        placeholders = ",".join("?" for _ in seqs)
        removed = self._conn.execute(
            f"DELETE FROM event_buffer WHERE seq IN ({placeholders})", seqs
        ).rowcount
        self._conn.commit()
        return removed

    def pending_count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM event_buffer").fetchone()[0])

    def close(self) -> None:
        self._conn.close()
