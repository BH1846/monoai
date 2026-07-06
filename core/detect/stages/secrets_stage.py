"""Secrets detection stage: API keys, tokens, private key blocks, passwords.

Split out from SENTINEL-2.0/pii_pipeline/rampart/regex.py's
`_detect_secrets` so secrets get their own detector-version string for
audit attribution (see DECISIONS.md).
"""
from __future__ import annotations

import re

from contracts.spans import SpanLabel, SpanSource

from detect.span import RawSpan

_SECRET_PATTERNS = [
    ("AWS_ACCESS_KEY", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("AWS_SECRET_KEY", re.compile(r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])")),
    ("GITHUB_TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,255}\b")),
    ("SLACK_TOKEN", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,72}\b")),
    ("GOOGLE_API_KEY", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("STRIPE_KEY", re.compile(r"\b(?:sk|pk)_(?:live|test)_[A-Za-z0-9]{16,64}\b")),
    ("PRIVATE_KEY_BLOCK", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b")),
]

_PASSWORD_CUE_RE = re.compile(
    r"(?:<password>|\bpass(?:word|code)?\b\s*[\"']?\s*[:=])\s*[\"']?"
    r"([^\s\"'<>]{4,40})",
    re.IGNORECASE,
)


class SecretsDetector:
    """Stateless; safe to reuse/share across calls and threads."""

    def detect(self, text: str) -> list[RawSpan]:
        spans: list[RawSpan] = []
        for name, pattern in _SECRET_PATTERNS:
            for m in pattern.finditer(text):
                spans.append(RawSpan(
                    start=m.start(), end=m.end(), text=m.group(0),
                    label=SpanLabel.SECRET, source=SpanSource.SECRETS,
                    confidence=0.97, meta={"secret_kind": name},
                ))
        taken = [(s.start, s.end) for s in spans]
        for m in _PASSWORD_CUE_RE.finditer(text):
            g_start, g_end = m.start(1), m.end(1)
            if any(a <= g_start < b or a < g_end <= b for a, b in taken):
                continue
            spans.append(RawSpan(
                start=g_start, end=g_end, text=m.group(1),
                label=SpanLabel.SECRET, source=SpanSource.SECRETS,
                confidence=0.75, meta={"secret_kind": "password_cue"},
            ))
            taken.append((g_start, g_end))
        return spans
