"""Evidence export: hash-chained JSONL bundle + a verify manifest.

Ed25519 signing (PyNaCl already a dependency via core/vault) is a Phase 2
stub — see DECISIONS.md. The bundle is still real and useful in Phase 1:
anyone can independently recompute the chain and confirm it verifies,
just without a cryptographic signature over the whole bundle yet.
"""
from __future__ import annotations

import json

from contracts.audit import AuditRecord

from audit.chain import verify


def export(records: list[AuditRecord]) -> bytes:
    manifest = {
        "record_count": len(records),
        "chain_verified": verify(records),
    }
    lines = [json.dumps(manifest, sort_keys=True)]
    lines.extend(record.model_dump_json() for record in records)
    return ("\n".join(lines) + "\n").encode("utf-8")


def sign_evidence(bundle: bytes, private_key) -> bytes:
    raise NotImplementedError("Ed25519-signed evidence export is Phase 2 — see DECISIONS.md")
