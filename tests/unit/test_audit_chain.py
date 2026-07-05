from contracts.audit import AuditRecord
from audit.chain import AuditChain, verify


class _MemorySink:
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    def write(self, record: AuditRecord) -> None:
        self.records.append(record)


def _record(**overrides) -> AuditRecord:
    data = dict(
        ts=1.0, request_id="r1", session_id="s1", event="completed",
        policy_id="default", policy_version="sha256:abc",
    )
    data.update(overrides)
    return AuditRecord(**data)


def test_hash_chain_links_records():
    sink = _MemorySink()
    chain = AuditChain(sink)

    chain.append(_record(request_id="r1"))
    chain.append(_record(request_id="r2"))
    chain.append(_record(request_id="r3"))

    assert sink.records[0].prev_hash is None
    assert sink.records[1].prev_hash == sink.records[0].hash
    assert sink.records[2].prev_hash == sink.records[1].hash
    assert verify(sink.records) is True


def test_verify_detects_tampering():
    sink = _MemorySink()
    chain = AuditChain(sink)
    chain.append(_record(request_id="r1"))
    chain.append(_record(request_id="r2"))

    tampered = sink.records[1].model_copy(update={"span_counts_by_label": {"EMAIL": 999}})
    records = [sink.records[0], tampered]
    assert verify(records) is False


def test_verify_empty_chain_is_valid():
    assert verify([]) is True
