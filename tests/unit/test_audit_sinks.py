from contracts.audit import AuditRecord
from audit.chain import AuditChain, verify
from audit.sinks import JsonlSink, read_jsonl, read_last_hash


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


def test_read_last_hash_missing_file_returns_none(tmp_path):
    assert read_last_hash(str(tmp_path / "does_not_exist.jsonl")) is None


def test_read_last_hash_matches_last_record(tmp_path):
    path = str(tmp_path / "audit.jsonl")
    chain = AuditChain(JsonlSink(path))
    chain.append(_record("r1"))
    last = chain.append(_record("r2"))

    assert read_last_hash(path) == last.hash


def test_chain_resumes_correctly_across_process_restart(tmp_path):
    """Regression test for a real bug found during manual end-to-end
    testing: every dev-server restart started a fresh AuditChain with
    prev_hash=None, breaking the chain link against records already in
    the file from the prior process. app.py must bootstrap
    initial_last_hash from the existing log on startup."""
    path = str(tmp_path / "audit.jsonl")

    chain_a = AuditChain(JsonlSink(path))
    chain_a.append(_record("r1"))
    chain_a.append(_record("r2"))

    # Simulate a process restart: a NEW AuditChain instance, bootstrapped
    # from the existing file's last hash (as gateway/app.py's lifespan does).
    chain_b = AuditChain(JsonlSink(path), initial_last_hash=read_last_hash(path))
    chain_b.append(_record("r3"))

    records = read_jsonl(path)
    assert len(records) == 3
    assert verify(records) is True
