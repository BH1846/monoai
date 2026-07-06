"""Hash-chained audit records: hash_n = sha256(hash_{n-1} || canonical_json(record_n)).

Implemented for real in Phase 1 (not deferred) — invariant #2 ("chain to
the previous record's hash") applies to all of Phase 1; only the
Postgres/webhook sinks and Ed25519-signed evidence export defer to
Phase 2 (see DECISIONS.md).
"""
from __future__ import annotations

import hashlib
import json

from contracts.audit import AuditRecord


def _canonical_json(record: AuditRecord) -> str:
    data = record.model_dump(exclude={"hash"}, mode="json")
    return json.dumps(data, sort_keys=True, default=str)


def compute_hash(prev_hash: str | None, record: AuditRecord) -> str:
    canonical = _canonical_json(record)
    return hashlib.sha256(((prev_hash or "") + canonical).encode("utf-8")).hexdigest()


class AuditChain:
    """Owns the running `last_hash` state and appends through a sink."""

    def __init__(self, sink, initial_last_hash: str | None = None) -> None:
        self._sink = sink
        self._last_hash = initial_last_hash

    def append(self, record: AuditRecord) -> AuditRecord:
        record = record.model_copy(update={"prev_hash": self._last_hash, "hash": None})
        h = compute_hash(self._last_hash, record)
        record = record.model_copy(update={"hash": h})
        self._sink.write(record)
        self._last_hash = h
        return record

    @property
    def last_hash(self) -> str | None:
        return self._last_hash


def verify(records: list[AuditRecord]) -> bool:
    """Walk the chain, recomputing each hash and comparing. Returns False
    on the first mismatch (wrong prev_hash link or a tampered field)."""
    prev_hash: str | None = None
    for record in records:
        if record.prev_hash != prev_hash:
            return False
        expected = compute_hash(prev_hash, record)
        if record.hash != expected:
            return False
        prev_hash = record.hash
    return True
