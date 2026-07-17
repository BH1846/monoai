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

from audit.signer import sign_record, verify_record

# Optional provenance fields added to AuditRecord AFTER records were already
# being persisted in the wild. For these, "key absent" and "key present but
# null" mean the SAME thing, so a None value is omitted from the canonical
# form entirely.
#
# WHY THIS EXISTS -- read before adding any field to AuditRecord:
# the canonical form is `model_dump()`, so it is coupled to the pydantic
# schema. Adding an optional field makes every ALREADY-WRITTEN record
# serialize with a `"new_field": null` key that wasn't there when its hash
# was computed -- silently invalidating the hash of every historical record
# and making verify() report the whole chain as TAMPERED. That is exactly
# what happened when `agent_id` was introduced: a real 108-record log failed
# verification, with record 0 hashing to f5d3bf59... instead of its stored
# 05a5d0f8... purely because of the extra null key.
#
# Omitting None-valued provenance fields makes such additions backward
# compatible by construction: an old record (field absent) and a new local
# record (field present, None) produce byte-identical canonical JSON. When a
# field IS set, it is included and therefore fully hash-covered/tamper-
# evident. Any new optional field must be added here too -- and
# tests/unit/test_audit_chain_compat.py pins that rule.
_OMIT_WHEN_NONE = ("agent_id", "origin_gateway")


def _canonical_json(record: AuditRecord) -> str:
    # "signature" is excluded alongside "hash": it's derived FROM the
    # hash (G13) and computed after compute_hash runs, so it can never
    # be part of what the hash covers -- otherwise every signed record
    # would hash differently than it did at write time (signature is
    # None during the initial compute, non-None once persisted).
    data = record.model_dump(exclude={"hash", "signature"}, mode="json")
    for field in _OMIT_WHEN_NONE:
        if data.get(field) is None:
            data.pop(field, None)
    return json.dumps(data, sort_keys=True, default=str)


def compute_hash(prev_hash: str | None, record: AuditRecord) -> str:
    canonical = _canonical_json(record)
    return hashlib.sha256(((prev_hash or "") + canonical).encode("utf-8")).hexdigest()


class AuditChain:
    """Owns the running `last_hash` state and appends through a sink.

    `signing_key`, when provided (MONOAI_AUDIT_SIGN=true), makes every
    appended record carry an Ed25519 signature over its own chain hash
    (G13) -- not just the hash chain itself. A tampered single record
    is then detectable in isolation, without replaying the whole chain.
    """

    def __init__(self, sink, initial_last_hash: str | None = None, signing_key=None) -> None:
        self._sink = sink
        self._last_hash = initial_last_hash
        self._signing_key = signing_key

    def append(self, record: AuditRecord) -> AuditRecord:
        record = record.model_copy(update={"prev_hash": self._last_hash, "hash": None, "signature": None})
        h = compute_hash(self._last_hash, record)
        record = record.model_copy(update={"hash": h})
        if self._signing_key is not None:
            record = record.model_copy(update={"signature": sign_record(record, self._signing_key)})
        self._sink.write(record)
        self._last_hash = h
        return record

    @property
    def last_hash(self) -> str | None:
        return self._last_hash


def verify(records: list[AuditRecord], public_key_hex: str | None = None) -> bool:
    """Walk the chain, recomputing each hash (and, if `public_key_hex`
    is given, each record's Ed25519 signature) and comparing. Returns
    False on the first mismatch (wrong prev_hash link, a tampered
    field, or -- when signature verification is requested -- a missing
    or invalid signature)."""
    prev_hash: str | None = None
    for record in records:
        if record.prev_hash != prev_hash:
            return False
        expected = compute_hash(prev_hash, record)
        if record.hash != expected:
            return False
        if public_key_hex is not None and not verify_record(record, public_key_hex):
            return False
        prev_hash = record.hash
    return True
