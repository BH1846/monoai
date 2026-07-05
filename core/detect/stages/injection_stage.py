"""Prompt-injection / jailbreak detection stage — Phase 2 (closes G4).

Phase 1 does not run this stage; `core/detect/pipeline.py` does not call it.
"""
from __future__ import annotations

from contracts.spans import DetectedSpan, TextUnit


def run(text_units: list[TextUnit]) -> list[DetectedSpan]:
    raise NotImplementedError("injection_stage is Phase 2 — see DECISIONS.md")
