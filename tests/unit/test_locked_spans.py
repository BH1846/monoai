from detect.stages.locked_span_stage import detect_locked_spans


def test_negated_email_marked_negated():
    spans = detect_locked_spans("not my email is john@example.com")
    assert len(spans) == 1
    assert spans[0].text == "john@example.com"
    assert spans[0].meta["negated"] is True
    # Structural guarantee: this stage no longer decides the action itself.
    assert "override_classification" not in spans[0].meta


def test_positive_anchor_not_negated():
    spans = detect_locked_spans("my email is john@example.com")
    assert len(spans) == 1
    assert spans[0].meta["negated"] is False


def test_negation_after_copula():
    spans = detect_locked_spans("my email is not john@example.com")
    assert len(spans) == 1
    assert spans[0].meta["negated"] is True


def test_negated_copula_contraction():
    spans = detect_locked_spans("my phone number isn't 555-123-4567")
    assert len(spans) == 1
    assert spans[0].meta["negated"] is True


def test_address_verb_anchor_negation():
    spans = detect_locked_spans("I no longer live at 742 Evergreen Terrace.")
    assert len(spans) == 1
    assert spans[0].text == "742 Evergreen Terrace"
    assert spans[0].meta["negated"] is True


def test_credit_card_negation_validates_luhn():
    spans = detect_locked_spans("my credit card is not 4111 1111 1111 1112")
    assert spans == []


def test_no_anchor_no_spans():
    assert detect_locked_spans("The weather is nice today.") == []


def test_username_anchor_detected():
    spans = detect_locked_spans("my username is jdoe_99")
    assert len(spans) == 1
    assert spans[0].text == "jdoe_99"


def test_date_of_birth_anchor_does_not_overcapture():
    spans = detect_locked_spans(
        "my date of birth is November 20th, 1934 and my username is jdoe_99"
    )
    by_text = {s.text for s in spans}
    assert "November 20th, 1934" in by_text
    assert "jdoe_99" in by_text
    assert not any("username" in s.text for s in spans)
