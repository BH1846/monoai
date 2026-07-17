"""Audit sinks: jsonl | postgres | webhook (SIEM) | forwarding (peer gateway).

`FanoutSink` lets one AuditChain feed several sinks, which is how audit
forwarding attaches itself: the local sink stays the source of truth and
`ForwardingSink` rides alongside it, rather than replacing it or adding a
second call site next to AuditChain.append().
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Protocol

import httpx
from contracts.audit import AuditRecord

logger = logging.getLogger(__name__)


class AuditSink(Protocol):
    def write(self, record: AuditRecord) -> None:
        ...


class FanoutSink:
    """Writes each record to several sinks in order.

    Order matters: the durable local sink goes FIRST, so the record is on
    local disk before any best-effort secondary (forwarding/SIEM) is
    attempted. A secondary that raises must not stop the ones after it or
    break AuditChain.append() -- secondaries are best-effort by contract, so
    their exceptions are swallowed and logged. The FIRST sink is treated as
    the primary and is allowed to raise (audit durability is fail-closed).
    """

    def __init__(self, sinks: list[AuditSink]) -> None:
        if not sinks:
            raise ValueError("FanoutSink requires at least one sink")
        self._primary, *self._secondaries = sinks

    def write(self, record: AuditRecord) -> None:
        self._primary.write(record)  # fail-closed: local durability first
        for sink in self._secondaries:
            try:
                sink.write(record)
            except Exception:  # noqa: BLE001 -- a SIEM/peer must never break the chain
                logger.warning("secondary audit sink failed", exc_info=True)

    def close(self) -> None:
        for sink in (self._primary, *self._secondaries):
            close = getattr(sink, "close", None)
            if close is not None:
                try:
                    close()
                except Exception:  # noqa: BLE001
                    logger.warning("audit sink close failed", exc_info=True)


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
    raises -- it must not affect the data path.

    NOTE: `write()` POSTs synchronously, and AuditChain.append() is called
    inline from the async orchestrator -- so a hung/unreachable webhook
    stalls the caller for the full timeout. That is tolerable for an
    opt-in best-effort SIEM feed, but it is exactly why ForwardingSink
    (below) does its network I/O on a background thread instead.
    """

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


class ForwardingSink:
    """Forwards this gateway's audit records to a peer "manager" gateway's
    ingest endpoint, with durable local buffering and retry.

    Unlike WebhookSink (best-effort, drops on failure) this guarantees
    eventual delivery: every record is enqueued to a durable local queue and
    removed only once the manager confirms a 2xx.

    ## `write()` never touches the network -- deliberately

    AuditChain.append() is called INLINE on the gateway's request path (see
    gateway/orchestrator.py). If write() POSTed synchronously, an unreachable
    manager would stall every chat request for the full HTTP timeout. So
    write() only does a local SQLite INSERT (comparable to JsonlSink's
    existing per-record fsync) and signals a background thread, which does
    the delivery. "Attempt immediately" is honoured -- the worker is woken on
    every write and does not wait for the sweep interval -- while the request
    path is structurally isolated from manager downtime rather than merely
    being fast most of the time.

    ## Ordering + at-least-once

    The worker drains oldest-first and STOPS at the first failure rather than
    skipping ahead, so records reach the manager in the order they were
    produced. Delivery is at-least-once (a lost response after the manager
    committed means a resend), so the ingest endpoint dedupes by record_id.
    """

    def __init__(
        self,
        url: str,
        admin_key: str,
        queue,
        gateway_id: str,
        interval_s: float = 30.0,
        timeout: float = 5.0,
        batch_size: int = 100,
        start_worker: bool = True,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._url = url
        self._queue = queue
        self._gateway_id = gateway_id
        self._interval_s = interval_s
        self._batch_size = batch_size
        # `transport` is injectable so tests can drive delivery against a mock
        # manager while still exercising the real auth/header wiring;
        # production passes None and gets a normal networked client.
        self._client = httpx.Client(
            timeout=timeout,
            headers={"Authorization": f"Bearer {admin_key}", "Content-Type": "application/json"},
            transport=transport,
        )
        self._wake = threading.Event()
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None
        if start_worker:
            self._thread = threading.Thread(target=self._run, name="audit-forwarder", daemon=True)
            self._thread.start()

    # -- request path (must be fast and must never raise) ------------------

    def write(self, record: AuditRecord) -> None:
        """Enqueue + wake the worker. No network I/O, never raises.

        The record is stamped with this gateway's id so the manager can tell
        it apart from its own records in the Audit Log. Its local copy (in
        the primary sink) keeps origin_gateway=None -- locally it IS local;
        only the forwarded copy carries the origin.
        """
        try:
            outbound = record.model_copy(update={"origin_gateway": self._gateway_id})
            self._queue.append(record.record_id, outbound.model_dump_json(), time.time())
            self._wake.set()
        except Exception:  # noqa: BLE001 -- forwarding must never break the chain
            # Nothing is truly lost: the primary sink already has this record
            # locally; only the forwarded copy is affected.
            logger.warning("failed to enqueue audit record for forwarding", exc_info=True)

    # -- background worker -------------------------------------------------

    def _run(self) -> None:  # pragma: no cover - exercised via drain_once in tests
        while not self._stopped.is_set():
            try:
                self.drain_once()
            except Exception:  # noqa: BLE001 -- the worker must never die
                logger.warning("audit forwarding sweep failed", exc_info=True)
            # Woken immediately by write(), otherwise retry on the interval.
            self._wake.wait(self._interval_s)
            self._wake.clear()

    def drain_once(self) -> int:
        """Deliver queued records oldest-first. Returns the number delivered.
        Stops at the first failure so ordering is preserved; the rest stay
        queued for the next sweep. Public so tests can drive a sweep
        deterministically without the thread."""
        delivered = 0
        while not self._stopped.is_set():
            batch = self._queue.peek_batch(self._batch_size)
            if not batch:
                break
            for item in batch:
                if not self._deliver(item.payload_json):
                    return delivered  # keep order: don't skip past a failure
                self._queue.ack([item.seq])
                delivered += 1
            if len(batch) < self._batch_size:
                break
        return delivered

    def _deliver(self, payload_json: str) -> bool:
        """POST one record. True only on a confirmed 2xx -- anything else
        (connection error, timeout, 4xx, 5xx) leaves it queued."""
        try:
            resp = self._client.post(self._url, content=payload_json)
        except httpx.HTTPError:
            return False
        return 200 <= resp.status_code < 300

    def close(self) -> None:
        self._stopped.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._client.close()
        close = getattr(self._queue, "close", None)
        if close is not None:
            close()
