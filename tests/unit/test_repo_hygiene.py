"""G14 local safety net: a fast regex scan over tracked files for secret-shaped
values. The real gate is the CI gitleaks job (.github/workflows/ci.yml); this
is a cheap pre-commit-speed check that doesn't require network access.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Deliberately narrow: real-looking secret shapes, not "any assignment".
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"sk-or-v1-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"VALKEY_PASSWORD=(?!change-me|\$\{|\$\(|ci-test)[^\s]{8,}"),
]

_ALLOWED_FILES = {".env.example"}


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return [line for line in out.stdout.splitlines() if line]


def test_no_secrets_in_tracked_files() -> None:
    offenders: list[str] = []
    for rel_path in _tracked_files():
        if Path(rel_path).name in _ALLOWED_FILES:
            continue
        full_path = REPO_ROOT / rel_path
        if not full_path.is_file():
            continue
        try:
            text = full_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in _SECRET_PATTERNS:
            if pattern.search(text):
                offenders.append(f"{rel_path}: matched {pattern.pattern}")

    assert not offenders, "possible committed secrets found:\n" + "\n".join(offenders)
