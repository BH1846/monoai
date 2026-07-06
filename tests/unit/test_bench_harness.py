"""G15 proof test: `make bench` produces bench/REPORT.md with the
expected tables."""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_bench_harness_produces_report():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "bench" / "run_all.py")],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr

    report_path = REPO_ROOT / "bench" / "REPORT.md"
    assert report_path.is_file()
    content = report_path.read_text()
    assert "PII detection" in content
    assert "Router accuracy" in content
    assert "Gateway end-to-end latency" in content
