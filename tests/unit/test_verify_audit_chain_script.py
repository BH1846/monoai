import subprocess
import sys
from pathlib import Path

from contracts.audit import AuditRecord
from audit.chain import AuditChain
from audit.sinks import JsonlSink

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "verify_audit_chain.py"


def _record(request_id: str) -> AuditRecord:
    return AuditRecord(
        ts=1.0, request_id=request_id, session_id="s1", event="completed",
        policy_id="default", policy_version="sha256:abc",
    )


def test_script_exits_zero_on_valid_chain(tmp_path):
    path = tmp_path / "audit.jsonl"
    chain = AuditChain(JsonlSink(str(path)))
    chain.append(_record("r1"))
    chain.append(_record("r2"))

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_script_exits_nonzero_on_tampered_chain(tmp_path):
    path = tmp_path / "audit.jsonl"
    chain = AuditChain(JsonlSink(str(path)))
    chain.append(_record("r1"))
    chain.append(_record("r2"))

    lines = path.read_text().splitlines()
    assert '"r2"' in lines[1]
    lines[1] = lines[1].replace('"r2"', '"TAMPERED"')
    path.write_text("\n".join(lines) + "\n")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1, result.stdout + result.stderr
