#!/usr/bin/env python3
"""One-off migration: re-chain a JSONL audit log under the current canonical
form (audit/chain.py's _canonical_json).

## Why this exists

Adding the optional `agent_id` field to AuditRecord changed the canonical
form: model_dump() started emitting `"agent_id": null`, a key that was not
present when older records' hashes were computed. Every historical record's
hash became unreproducible and verify() reported the whole chain TAMPERED.

The fix in audit/chain.py omits None-valued provenance fields from the
canonical form, so "key absent" (old record) and "key present but null"
(new record) hash identically. That restores every record written BEFORE the
field was introduced with no data change at all.

It does NOT restore the handful of records written in the window AFTER the
field landed but BEFORE the fix: those had `"agent_id": null` genuinely baked
into their stored hash. This script recomputes those, and only those.

## What it does

Walks the log in order and re-chains every record (prev_hash = running last
hash, hash = compute_hash(...)). Records whose stored hash already matches
the current canonical form are byte-identical afterwards -- this is a no-op
for them. Only the records from the broken window change.

It is idempotent: running it twice is a no-op the second time.

## Safety

  * Refuses to touch a log containing signed records (re-hashing would
    invalidate every signature and this script has no signing key).
  * Writes a timestamped .bak next to the log before modifying anything.
  * Writes atomically via a temp file + rename.
  * Verifies the result before replacing the original, and aborts if the
    re-chained log does not verify.

Usage:
    python scripts/rehash_audit_chain.py gateway_audit.jsonl [--dry-run]
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

from audit.chain import compute_hash, verify
from contracts.audit import AuditRecord


def _load(path: Path) -> list[AuditRecord]:
    records: list[AuditRecord] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(AuditRecord.model_validate_json(line))
    return records


def rechain(records: list[AuditRecord]) -> tuple[list[AuditRecord], int]:
    """Re-link + re-hash the chain under the CURRENT canonical form.
    Returns (records, changed_count)."""
    out: list[AuditRecord] = []
    prev_hash: str | None = None
    changed = 0
    for record in records:
        fixed = record.model_copy(update={"prev_hash": prev_hash, "hash": None})
        new_hash = compute_hash(prev_hash, fixed)
        fixed = fixed.model_copy(update={"hash": new_hash})
        if fixed.hash != record.hash or fixed.prev_hash != record.prev_hash:
            changed += 1
        out.append(fixed)
        prev_hash = new_hash
    return out, changed


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    path = Path(argv[0])
    dry_run = "--dry-run" in argv

    if not path.is_file():
        print(f"no such audit log: {path}", file=sys.stderr)
        return 1

    records = _load(path)
    if not records:
        print("log is empty; nothing to do")
        return 0

    signed = [r.record_id for r in records if r.signature is not None]
    if signed:
        print(
            f"REFUSING: {len(signed)} record(s) carry an Ed25519 signature. Re-hashing would "
            "invalidate them and this script cannot re-sign. Rotate the log instead.",
            file=sys.stderr,
        )
        return 1

    if verify(records):
        print(f"{path}: already verifies under the current canonical form ({len(records)} records) -- nothing to do")
        return 0

    fixed, changed = rechain(records)
    if not verify(fixed):
        print("ABORT: re-chained log still does not verify; original left untouched", file=sys.stderr)
        return 1

    print(f"{path}: {len(records)} records, {changed} need re-hashing, {len(records) - changed} unchanged")
    if dry_run:
        print("--dry-run: no files written")
        return 0

    backup = path.with_suffix(path.suffix + f".bak-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(path, backup)
    print(f"backup written: {backup}")

    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for record in fixed:
            f.write(record.model_dump_json() + "\n")
    tmp.replace(path)

    reloaded = _load(path)
    if not verify(reloaded):
        print("ABORT: reloaded log does not verify -- restore from the backup above", file=sys.stderr)
        return 1
    print(f"{path}: OK -- chain verifies ({len(reloaded)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
