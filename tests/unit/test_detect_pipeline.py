from contracts.spans import DetectedSpan, SpanLabel, TextUnit, TextUnitLocator
from detect.pipeline import DetectionPipeline


def _unit(unit_id: str, text: str, turn_index: int = 0, role: str = "user") -> TextUnit:
    return TextUnit(
        unit_id=unit_id,
        role=role,
        text=text,
        locator=TextUnitLocator(surface="chat_message", path=f"messages[{turn_index}].content"),
        turn_index=turn_index,
        direction="input",
    )


def test_email_and_phone_detected_with_label_and_confidence_only():
    pipeline = DetectionPipeline(use_onnx_ner=False)
    spans = pipeline.run([_unit("u1", "email me at a@b.com or call 555-123-4567")])

    labels = {s.label for s in spans}
    assert SpanLabel.EMAIL in labels
    assert SpanLabel.PHONE in labels
    for s in spans:
        assert isinstance(s, DetectedSpan)
        assert not hasattr(s, "action")
        assert not hasattr(s, "classification")
        assert s.confidence >= 0.0


def test_per_text_unit_negation_scoping_does_not_bleed_across_messages():
    pipeline = DetectionPipeline(use_onnx_ner=False)
    units = [
        _unit("u1", "not my email is a@b.com", turn_index=0),
        _unit("u2", "my email is a@b.com", turn_index=1),
    ]
    spans = pipeline.run(units)

    u1_email = next(s for s in spans if s.unit_id == "u1" and s.label == SpanLabel.EMAIL)
    u2_email = next(s for s in spans if s.unit_id == "u2" and s.label == SpanLabel.EMAIL)

    assert u1_email.meta.get("negated") is True
    assert u2_email.meta.get("negated") is False
