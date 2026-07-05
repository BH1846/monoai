from contracts.spans import SpanLabel, SpanSource
from detect.span import RawSpan
from detect.stages.span_merge import merge_spans


def _span(start, end, label, source, confidence=0.9, text=""):
    return RawSpan(start=start, end=end, text=text, label=label, source=source, confidence=confidence)


def test_locked_wins_over_overlapping_detected_span():
    detected = _span(0, 16, SpanLabel.EMAIL, SpanSource.REGEX, confidence=0.98, text="john@example.com")
    locked_span = _span(0, 16, SpanLabel.EMAIL, SpanSource.LOCKED, confidence=0.9, text="john@example.com")
    merged = merge_spans([locked_span], [detected])
    assert len(merged) == 1
    assert merged[0].source == SpanSource.LOCKED


def test_non_overlapping_spans_both_kept():
    a = _span(0, 5, SpanLabel.EMAIL, SpanSource.REGEX)
    b = _span(20, 25, SpanLabel.PHONE, SpanSource.REGEX)
    merged = merge_spans([], [a, b])
    assert len(merged) == 2


def test_locked_locked_conflict_resolved_by_confidence():
    low = _span(0, 10, SpanLabel.PERSON, SpanSource.LOCKED, confidence=0.5)
    high = _span(2, 12, SpanLabel.PERSON, SpanSource.LOCKED, confidence=0.9)
    merged = merge_spans([low, high], [])
    assert len(merged) == 1
    assert merged[0].confidence == 0.9


def test_empty_inputs():
    assert merge_spans([], []) == []
