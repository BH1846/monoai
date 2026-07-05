"""Span-repair stage: fixes boundary errors, merges split entities, resolves
overlaps between regex/secrets/ner spans.

Ported from SENTINEL-2.0/pii_pipeline/rampart/span_repair.py.

Regex/secrets/NER run independently and can each produce spans with:
  - boundary errors (a phone/ID number partially caught because of an
    unusual separator, a name cut mid-token by an off-by-one offset)
  - entities split across two adjacent spans
  - overlapping/conflicting spans

This stage fixes all three, deterministically, in a single
sort-then-linear-scan pass: O(n log n) from the sort, O(n) for everything
else, where n = number of raw candidate spans (not text length).
"""
from __future__ import annotations

import re

from contracts.spans import SpanLabel, SpanSource
from detect.span import RawSpan

_DIGIT_RUN_LABELS = {SpanLabel.PHONE, SpanLabel.CREDIT_CARD, SpanLabel.GOV_ID}

_WORD_SNAP_LABELS = {
    SpanLabel.PERSON, SpanLabel.ADDRESS, SpanLabel.ORG, SpanLabel.MISC,
    SpanLabel.USERNAME, SpanLabel.TITLE, SpanLabel.DEMOGRAPHIC,
}

_WORD_CHAR_RE = re.compile(r"[A-Za-z0-9']")
_DIGIT_OR_SEP_RE = re.compile(r"[\d\-.\s()]")
_DIGIT_RE = re.compile(r"\d")

_LABEL_PRIORITY = {
    SpanLabel.SECRET: 10,
    SpanLabel.CREDIT_CARD: 9,
    SpanLabel.GOV_ID: 8,
    SpanLabel.EMAIL: 7,
    SpanLabel.PHONE: 6,
    SpanLabel.IP_ADDRESS: 5,
    SpanLabel.DATE_TIME: 5,
    SpanLabel.USERNAME: 5,
    SpanLabel.ADDRESS: 4,
    SpanLabel.ORG: 3,
    SpanLabel.PERSON: 2,
    SpanLabel.TITLE: 2,
    SpanLabel.DEMOGRAPHIC: 1,
    SpanLabel.MISC: 1,
}

_MERGEABLE_GAP_RE = re.compile(r"^[\s,]{1,3}$")


def _extend_digit_span(span: RawSpan, text: str) -> RawSpan:
    orig_start, orig_end = span.start, span.end
    start, end = orig_start, orig_end
    while start > 0 and _DIGIT_OR_SEP_RE.match(text[start - 1]) and _DIGIT_RE.search(text[max(0, start - 3):start]):
        start -= 1
    while end < len(text) and _DIGIT_OR_SEP_RE.match(text[end]) and _DIGIT_RE.search(text[end:end + 3]):
        end += 1
    while start < orig_start and not text[start].isdigit():
        start += 1
    while end > orig_end and not text[end - 1].isdigit():
        end -= 1
    if (start, end) == (span.start, span.end):
        return span
    return RawSpan(
        start=start, end=end, text=text[start:end], label=span.label,
        source=SpanSource.REPAIRED, confidence=span.confidence,
        meta={**span.meta, "repaired": "digit_extend"},
    )


def _snap_word_boundary(span: RawSpan, text: str) -> RawSpan:
    start, end = span.start, span.end
    while start > 0 and _WORD_CHAR_RE.match(text[start - 1]):
        start -= 1
    while end < len(text) and _WORD_CHAR_RE.match(text[end]):
        end += 1
    if (start, end) == (span.start, span.end):
        return span
    return RawSpan(
        start=start, end=end, text=text[start:end], label=span.label,
        source=SpanSource.REPAIRED, confidence=span.confidence,
        meta={**span.meta, "repaired": "word_snap"},
    )


def _merge_adjacent_same_label(spans: list[RawSpan], text: str) -> list[RawSpan]:
    if not spans:
        return spans
    merged = [spans[0]]
    for span in spans[1:]:
        prev = merged[-1]
        if span.label == prev.label and span.start >= prev.end:
            gap = text[prev.end:span.start]
            if _MERGEABLE_GAP_RE.match(gap):
                merged[-1] = RawSpan(
                    start=prev.start, end=span.end, text=text[prev.start:span.end],
                    label=prev.label, source=SpanSource.REPAIRED,
                    confidence=max(prev.confidence, span.confidence),
                    meta={**prev.meta, "repaired": "gap_merge"},
                )
                continue
        merged.append(span)
    return merged


def _overlap_len(a: RawSpan, b: RawSpan) -> int:
    return max(0, min(a.end, b.end) - max(a.start, b.start))


def _score(span: RawSpan) -> float:
    return span.confidence + _LABEL_PRIORITY.get(span.label, 0) * 1e-4


def _resolve_overlaps(spans: list[RawSpan]) -> list[RawSpan]:
    if not spans:
        return spans
    spans = sorted(spans, key=lambda s: s.start)
    resolved: list[RawSpan] = [spans[0]]
    for span in spans[1:]:
        prev = resolved[-1]
        if not span.overlaps(prev):
            resolved.append(span)
            continue

        overlap = _overlap_len(span, prev)
        shorter = min(span.length, prev.length)
        significant = shorter > 0 and (overlap / shorter) > 0.4

        if span.label == prev.label:
            resolved[-1] = RawSpan(
                start=min(prev.start, span.start), end=max(prev.end, span.end),
                text="", label=prev.label, source=SpanSource.REPAIRED,
                confidence=max(prev.confidence, span.confidence),
                meta={**prev.meta, "repaired": "overlap_union"},
            )
            continue

        if significant:
            winner = prev if _score(prev) >= _score(span) else span
            resolved[-1] = winner
            continue

        if span.end > prev.end:
            trimmed_start = prev.end
            if trimmed_start < span.end:
                resolved.append(RawSpan(
                    start=trimmed_start, end=span.end, text=span.text[trimmed_start - span.start:],
                    label=span.label, source=SpanSource.REPAIRED,
                    confidence=span.confidence,
                    meta={**span.meta, "repaired": "boundary_trim"},
                ))
    return resolved


def repair_spans(spans: list[RawSpan], text: str) -> list[RawSpan]:
    """Fix boundary errors, merge split entities, resolve overlaps.

    O(n log n) where n = len(spans) (dominated by the initial sort).
    """
    if not spans:
        return []

    fixed = []
    for span in spans:
        if span.label in _DIGIT_RUN_LABELS:
            fixed.append(_extend_digit_span(span, text))
        elif span.label in _WORD_SNAP_LABELS:
            fixed.append(_snap_word_boundary(span, text))
        else:
            fixed.append(span)

    fixed.sort(key=lambda s: (s.start, -s.length))
    merged = _merge_adjacent_same_label(fixed, text)
    resolved = _resolve_overlaps(merged)

    final = []
    for s in resolved:
        if not s.text:
            s = RawSpan(start=s.start, end=s.end, text=text[s.start:s.end], label=s.label,
                        source=s.source, confidence=s.confidence, meta=s.meta)
        final.append(s)
    return sorted(final, key=lambda s: s.start)
