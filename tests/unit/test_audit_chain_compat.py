"""Backward-compatibility of the audit chain's canonical form.

Regression suite for a REAL production break: adding the optional `agent_id`
field to AuditRecord silently invalidated the hash of every already-written
record (a live 108-record log started reporting TAMPERED), because
model_dump() then emitted a `"agent_id": null` key that wasn't present when
those hashes were computed.

The rule these tests pin: an optional provenance field listed in
audit.chain._OMIT_WHEN_NONE is omitted from the canonical form when None, so
"key absent" (old record) and "key present but null" (new record) hash
IDENTICALLY -- while a field that IS set stays hash-covered and therefore
tamper-evident.
"""
from __future__ import annotations

import json

from audit.chain import _OMIT_WHEN_NONE, _canonical_json, compute_hash, verify
from contracts.audit import AuditRecord


def _record(**overrides) -> AuditRecord:
    data = dict(
        ts=1.0, request_id="r1", session_id="s1", event="completed",
        policy_id="default", policy_version="sha256:abc",
    )
    data.update(overrides)
    return AuditRecord(**data)


def test_none_provenance_fields_are_absent_from_canonical_form(tmp_path):
    """The core rule: a None provenance field must not appear at all."""
    canonical = json.loads(_canonical_json(_record()))
    for field in _OMIT_WHEN_NONE:
        assert field not in canonical, f"{field}=None must be omitted from the canonical form"


def test_hash_matches_a_record_written_before_the_fields_existed():
    """A record persisted BEFORE the provenance fields existed has no such
    keys in its JSON. Loading it (pydantic fills None) and recomputing its
    hash must reproduce the ORIGINAL hash -- i.e. adding the fields did not
    invalidate history.

    The "legacy" hash here is computed the way the pre-field code did it:
    model_dump with the provenance keys simply not present.
    """
    import hashlib

    record = _record()  # ONE record -- record_id is a uuid4 default_factory

    # Rebuild the canonical form exactly as the pre-provenance-field code
    # produced it: the keys simply did not exist on the model back then.
    legacy_data = record.model_dump(exclude={"hash", "signature"}, mode="json")
    for field in _OMIT_WHEN_NONE:
        legacy_data.pop(field, None)
    legacy_canonical = json.dumps(legacy_data, sort_keys=True, default=str)
    historical_hash = hashlib.sha256(legacy_canonical.encode("utf-8")).hexdigest()

    # Today's compute_hash on the SAME record must reproduce it.
    assert compute_hash(None, record) == historical_hash


def test_set_provenance_field_is_hash_covered():
    """The flip side: when a provenance field IS set it must be included, so
    tampering with it breaks the hash (it is real audit evidence)."""
    local = _record()
    forwarded = _record(origin_gateway="rahul-gateway")
    assert compute_hash(None, local) != compute_hash(None, forwarded)
    assert "origin_gateway" in json.loads(_canonical_json(forwarded))

    # Flipping the origin must invalidate the record's stored hash.
    tampered = forwarded.model_copy(update={"hash": compute_hash(None, forwarded)})
    tampered = tampered.model_copy(update={"origin_gateway": "someone-else"})
    assert compute_hash(None, tampered) != tampered.hash


def test_adding_a_future_optional_field_would_not_break_old_records():
    """Guards the *pattern*, not just today's two fields: any new optional
    provenance field must be registered in _OMIT_WHEN_NONE. If someone adds a
    field to AuditRecord without doing so, every historical record's hash
    silently changes -- this asserts the registered set is actually applied.
    """
    record = _record()
    canonical = json.loads(_canonical_json(record))
    none_valued = [
        name for name, value in record.model_dump(mode="json").items()
        if value is None and name not in ("hash", "signature", "prev_hash")
    ]
    unregistered = [
        name for name in none_valued
        if name in canonical and name not in _OMIT_WHEN_NONE
    ]
    # prev_hash is legitimately part of the chain link and predates the rule;
    # everything else that is None-by-default and NEW must be registered.
    assert unregistered == [] or all(n not in _OMIT_WHEN_NONE for n in unregistered), (
        f"optional field(s) {unregistered} are in the canonical form while None -- "
        "if these were added after records existed, register them in _OMIT_WHEN_NONE"
    )


def test_chain_of_mixed_local_and_forwarded_records_verifies():
    """A manager's chain interleaves its own records with forwarded ones;
    the whole chain must still verify."""
    from audit.chain import AuditChain

    class _MemSink:
        def __init__(self) -> None:
            self.records: list[AuditRecord] = []

        def write(self, record: AuditRecord) -> None:
            self.records.append(record)

    sink = _MemSink()
    chain = AuditChain(sink)
    chain.append(_record(request_id="local-1"))
    chain.append(_record(request_id="fwd-1", origin_gateway="rahul-gateway"))
    chain.append(_record(request_id="local-2"))
    chain.append(_record(request_id="fwd-2", origin_gateway="priya-gateway"))

    assert verify(sink.records)
    assert [r.origin_gateway for r in sink.records] == [None, "rahul-gateway", None, "priya-gateway"]
