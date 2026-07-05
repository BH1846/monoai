from contracts.audit import AuditRecord
from audit.sinks import JsonlSink, read_jsonl


def _record(request_id: str) -> AuditRecord:
    return AuditRecord(
        ts=1.0, request_id=request_id, session_id="s1", event="completed",
        policy_id="default", policy_version="sha256:abc",
    )


def test_jsonl_sink_one_line_per_record(tmp_path):
    path = tmp_path / "audit.jsonl"
    sink = JsonlSink(str(path))
    sink.write(_record("r1"))
    sink.write(_record("r2"))

    lines = path.read_text().splitlines()
    assert len(lines) == 2

    records = read_jsonl(str(path))
    assert [r.request_id for r in records] == ["r1", "r2"]
