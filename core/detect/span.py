"""Internal detection-time span representation.

Detector stages (regex/secrets/ner/span_repair/locked_span) operate on
`RawSpan` — a lightweight, unit_id-less mirror of the old
SENTINEL-2.0/pii_pipeline `Span` dataclass — since a single stage call
processes one TextUnit's text at a time and doesn't need to know which
unit_id it belongs to. `core/detect/pipeline.py` attaches `unit_id` only
when converting the final merged spans into `contracts.spans.DetectedSpan`
for the caller.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from contracts.spans import SpanLabel, SpanSource


@dataclass
class RawSpan:
    """A half-open character span [start, end) over some text."""

    start: int
    end: int
    text: str
    label: SpanLabel
    source: SpanSource
    confidence: float = 1.0
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def length(self) -> int:
        return self.end - self.start

    def overlaps(self, other: RawSpan) -> bool:
        return self.start < other.end and other.start < self.end
