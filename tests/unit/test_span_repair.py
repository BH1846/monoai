from contracts.spans import SpanLabel, SpanSource
from detect.span import RawSpan
from detect.stages.span_repair import repair_spans


def test_extends_partially_caught_phone_number():
    text = "call 555-123-45678 now"
    truncated = RawSpan(start=5, end=16, text=text[5:16], label=SpanLabel.PHONE,
                         source=SpanSource.REGEX, confidence=0.9)
    repaired = repair_spans([truncated], text)
    assert len(repaired) == 1
    assert repaired[0].text == "555-123-45678"


def test_does_not_strip_original_leading_paren():
    text = "Phone (555) 123-4567 today"
    span = RawSpan(start=6, end=20, text=text[6:20], label=SpanLabel.PHONE,
                    source=SpanSource.REGEX, confidence=0.93)
    repaired = repair_spans([span], text)
    assert repaired[0].text == "(555) 123-4567"


def test_merges_adjacent_same_label_spans():
    text = "John Smith is here"
    first = RawSpan(start=0, end=4, text="John", label=SpanLabel.PERSON,
                     source=SpanSource.NER, confidence=0.8)
    second = RawSpan(start=5, end=10, text="Smith", label=SpanLabel.PERSON,
                      source=SpanSource.NER, confidence=0.8)
    repaired = repair_spans([first, second], text)
    assert len(repaired) == 1
    assert repaired[0].text == "John Smith"


def test_resolves_overlap_by_confidence_and_priority():
    text = "742 Evergreen Terrace is the address"
    address = RawSpan(start=0, end=21, text=text[0:21], label=SpanLabel.ADDRESS,
                       source=SpanSource.NER, confidence=0.8)
    person_guess = RawSpan(start=4, end=21, text=text[4:21], label=SpanLabel.PERSON,
                            source=SpanSource.NER, confidence=0.55)
    repaired = repair_spans([address, person_guess], text)
    assert len(repaired) == 1
    assert repaired[0].label == SpanLabel.ADDRESS


def test_word_boundary_snap_fixes_off_by_one():
    text = "Contact John Doe please"
    span = RawSpan(start=9, end=16, text=text[9:16], label=SpanLabel.PERSON,
                    source=SpanSource.NER, confidence=0.7)
    assert span.text == "ohn Doe"
    repaired = repair_spans([span], text)
    assert repaired[0].text == "John Doe"


def test_empty_input():
    assert repair_spans([], "some text") == []
