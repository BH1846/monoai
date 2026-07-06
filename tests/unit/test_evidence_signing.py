"""G10 proof tests: hash-chain tamper detection (chain.py already covers
this in test_audit_chain.py) + Ed25519 evidence signing."""
from contracts.audit import AuditRecord
from audit.chain import AuditChain, verify
from audit.evidence import export, sign_evidence, verify_signature
from audit.signing import load_or_create_signing_key
from audit.sinks import JsonlSink


class _FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def get(self, key: str):
        return self._store.get(key)

    def set(self, key: str, value: bytes, nx: bool = False):
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True


def _record(request_id: str) -> AuditRecord:
    return AuditRecord(
        ts=1.0, request_id=request_id, session_id="s1", event="completed",
        policy_id="default", policy_version="sha256:abc",
    )


def test_chain_verifies_and_tamper_detected(tmp_path):
    path = str(tmp_path / "audit.jsonl")
    chain = AuditChain(JsonlSink(path))
    chain.append(_record("r1"))
    chain.append(_record("r2"))

    from audit.sinks import read_jsonl
    records = read_jsonl(path)
    assert verify(records) is True

    tampered = records[1].model_copy(update={"span_counts_by_label": {"EMAIL": 999}})
    assert verify([records[0], tampered]) is False


def test_evidence_export_bundle_schema(tmp_path):
    chain = AuditChain(JsonlSink(str(tmp_path / "audit.jsonl")))
    chain.append(_record("r1"))
    chain.append(_record("r2"))

    from audit.sinks import read_jsonl
    records = read_jsonl(str(tmp_path / "audit.jsonl"))
    bundle = export(records)

    import json
    lines = bundle.decode("utf-8").strip().split("\n")
    manifest = json.loads(lines[0])
    assert manifest["record_count"] == 2
    assert manifest["chain_verified"] is True
    assert len(lines) == 3  # manifest + 2 records


def test_sign_and_verify_roundtrip():
    signing_key = load_or_create_signing_key(_FakeRedis(), key_name="test:signing_key")
    bundle = b"some evidence bundle bytes"

    sig = sign_evidence(bundle, signing_key)
    assert verify_signature(bundle, sig["signature"], sig["public_key"]) is True


def test_tampered_bundle_fails_signature_verification():
    signing_key = load_or_create_signing_key(_FakeRedis(), key_name="test:signing_key")
    bundle = b"some evidence bundle bytes"
    sig = sign_evidence(bundle, signing_key)

    tampered_bundle = b"some evidence bundle BYTES-TAMPERED"
    assert verify_signature(tampered_bundle, sig["signature"], sig["public_key"]) is False


def test_signing_key_persists_across_instances():
    redis = _FakeRedis()
    key_a = load_or_create_signing_key(redis, key_name="test:signing_key")
    key_b = load_or_create_signing_key(redis, key_name="test:signing_key")
    assert bytes(key_a) == bytes(key_b)
