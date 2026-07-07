"""Audit sinks: jsonl | postgres | webhook (SIEM)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

import httpx

from contracts.audit import AuditRecord


class AuditSink(Protocol):
    def write(self, record: AuditRecord) -> None:
        ...


class JsonlSink:
    """Append-only JSONL, one record per line. fsync after every write --
    the data path is fail-closed, so audit durability matters more than
    write throughput here."""

    def __init__(self, path: str = "./gateway_audit.jsonl") -> None:
        self._path = Path(path)

    def write(self, record: AuditRecord) -> None:
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")
            f.flush()
            os.fsync(f.fileno())


class UnsignedAuditRecordError(Exception):
    """Raised by read_jsonl/PostgresSink.read_all when require_signature=True
    (MONOAI_AUDIT_SIGN=true) and a record lacks a signature -- G13's
    "reject unsigned entries" reading-side enforcement."""

    def __init__(self, record_id: str) -> None:
        super().__init__(f"unsigned audit record found while signing is required: {record_id}")
        self.record_id = record_id


def read_jsonl(path: str, require_signature: bool = False) -> list[AuditRecord]:
    records: list[AuditRecord] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = AuditRecord.model_validate_json(line)
            if require_signature and record.signature is None:
                raise UnsignedAuditRecordError(record.record_id)
            records.append(record)
    return records


def read_last_hash(path: str) -> str | None:
    """Bootstraps AuditChain.last_hash across a process restart: without
    this, a fresh AuditChain(initial_last_hash=None) appending to an
    EXISTING jsonl file would write a record whose prev_hash=None doesn't
    match the file's actual last hash, breaking the chain at every
    restart -- a real gap found during manual end-to-end testing (every
    dev-server restart during this session corrupted the demo chain)."""
    if not Path(path).is_file():
        return None
    last_hash: str | None = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            last_hash = AuditRecord.model_validate_json(line).hash
    return last_hash


_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table} (
    record_id TEXT PRIMARY KEY,
    ts DOUBLE PRECISION NOT NULL,
    request_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    event TEXT NOT NULL,
    prev_hash TEXT,
    hash TEXT,
    data JSONB NOT NULL
)
"""


class PostgresSink:
    """Sync (psycopg3, not asyncpg -- see DECISIONS.md): AuditSink.write()
    is a synchronous protocol method used from within already-async
    orchestrator code without an `await`; switching to asyncpg would
    require threading async/await through AuditChain.append and every
    call site, a wider refactor not worth it for Phase 2's scope."""

    def __init__(self, dsn: str, table: str = "audit_records") -> None:
        import psycopg

        self._table = table
        self._conn = psycopg.connect(dsn, autocommit=True)
        self._conn.execute(_PG_SCHEMA.format(table=table))

    def write(self, record: AuditRecord) -> None:
        self._conn.execute(
            f"INSERT INTO {self._table} "
            "(record_id, ts, request_id, session_id, event, prev_hash, hash, data) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                record.record_id, record.ts, record.request_id, record.session_id, record.event,
                record.prev_hash, record.hash, record.model_dump_json(),
            ),
        )

    def read_all(self, require_signature: bool = False) -> list[AuditRecord]:
        rows = self._conn.execute(f"SELECT data FROM {self._table} ORDER BY ts ASC").fetchall()
        records = [AuditRecord.model_validate_json(row[0]) for row in rows]
        if require_signature:
            for record in records:
                if record.signature is None:
                    raise UnsignedAuditRecordError(record.record_id)
        return records

    def close(self) -> None:
        self._conn.close()


class WebhookSink:
    """Fail-open (invariant #3): a SIEM/webhook delivery failure never
    raises -- it must not affect the data path."""

    def __init__(self, url: str, timeout: float = 5.0) -> None:
        self._url = url
        self._client = httpx.Client(timeout=timeout)

    def write(self, record: AuditRecord) -> None:
        try:
            self._client.post(self._url, json=record.model_dump(mode="json"))
        except httpx.HTTPError:
            pass

    def close(self) -> None:
        self._client.close()
