"""Audit sinks: jsonl (real) | postgres | webhook (Phase 2 stubs)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

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


def read_jsonl(path: str) -> list[AuditRecord]:
    records: list[AuditRecord] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(AuditRecord.model_validate_json(line))
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


class PostgresSink:
    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError("postgres audit sink is Phase 2 — see DECISIONS.md")

    def write(self, record: AuditRecord) -> None:
        raise NotImplementedError("postgres audit sink is Phase 2 — see DECISIONS.md")


class WebhookSink:
    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError("webhook (SIEM) audit sink is Phase 2 — see DECISIONS.md")

    def write(self, record: AuditRecord) -> None:
        raise NotImplementedError("webhook (SIEM) audit sink is Phase 2 — see DECISIONS.md")
