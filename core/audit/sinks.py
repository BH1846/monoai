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
