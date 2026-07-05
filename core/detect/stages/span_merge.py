"""span_merge: combine locked_span_stage output with regex/secrets/ner
(post span_repair) spans.

Ported verbatim from SENTINEL-2.0/pii_pipeline/span_merge.py.

Precedence rule: LOCKED always wins over regex/secrets/ner on any
character-range conflict, full stop — no confidence comparison. Any
non-LOCKED span that overlaps a locked span is dropped in favor of the
locked span.
"""
from __future__ import annotations

from detect.span import RawSpan


def _resolve_locked_overlaps(locked: list[RawSpan]) -> list[RawSpan]:
    """Locked spans conflicting with each other (rare) resolve by
    confidence, same tie-break style as span_repair."""
    ordered = sorted(locked, key=lambda s: s.start)
    accepted: list[RawSpan] = []
    for span in ordered:
        conflict_idx = None
        for i, existing in enumerate(accepted):
            if existing.overlaps(span):
                conflict_idx = i
                break
        if conflict_idx is None:
            accepted.append(span)
            continue
        existing = accepted[conflict_idx]
        if span.confidence > existing.confidence:
            accepted[conflict_idx] = span
    return accepted


def merge_spans(locked: list[RawSpan], detected: list[RawSpan]) -> list[RawSpan]:
    locked_resolved = _resolve_locked_overlaps(locked)
    result = list(detected)
    for locked_span in sorted(locked_resolved, key=lambda s: s.start):
        result = [r for r in result if not r.overlaps(locked_span)]
        result.append(locked_span)
    return sorted(result, key=lambda s: s.start)
