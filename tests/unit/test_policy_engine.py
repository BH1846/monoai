from contracts.policy import Action
from contracts.spans import DetectedSpan, SpanLabel, SpanSource
from policy.engine import evaluate
from policy.schema import Policy

_POLICY_DICT = {
    "policy_id": "test",
    "detectors": {"packs": ["base_en"]},
    "rules": {
        "SECRET": {"action": "BLOCK"},
        "EMAIL": {"action": "REVERSIBLE"},
        "PERSON": {
            "action": "REVERSIBLE",
            "min_confidence": 0.6,
            "below_min_confidence_action": "PRESERVE",
        },
        "ORG": {"action": "PRESERVE"},
    },
    "overrides": {
        "locked_span_negation": {"when_meta_negated": True, "action": "PRESERVE"},
    },
    "compressible_length_threshold": 20,
}


def _span(label, source=SpanSource.REGEX, confidence=1.0, meta=None, start=0, end=5, text="x"):
    return DetectedSpan(
        unit_id="u1", start=start, end=end, text=text, label=label, source=source,
        confidence=confidence, meta=meta or {},
    )


def test_secret_always_blocks_regardless_of_policy():
    policy = Policy(**_POLICY_DICT)
    decisions = evaluate([_span(SpanLabel.SECRET)], policy)
    assert decisions[0].action == Action.BLOCK


def test_low_confidence_ner_person_downgrades_to_preserve():
    policy = Policy(**_POLICY_DICT)
    decisions = evaluate([_span(SpanLabel.PERSON, source=SpanSource.NER, confidence=0.4)], policy)
    assert decisions[0].action == Action.PRESERVE
    assert decisions[0].rule_id == "PERSON:below_min_confidence"


def test_high_confidence_ner_person_stays_reversible():
    policy = Policy(**_POLICY_DICT)
    decisions = evaluate([_span(SpanLabel.PERSON, source=SpanSource.NER, confidence=0.9)], policy)
    assert decisions[0].action == Action.REVERSIBLE


def test_negated_span_overridden_to_preserve():
    policy = Policy(**_POLICY_DICT)
    decisions = evaluate([_span(SpanLabel.EMAIL, meta={"negated": True})], policy)
    assert decisions[0].action == Action.PRESERVE
    assert decisions[0].rule_id == "locked_span_negation"


def test_unlisted_label_defaults_to_preserve():
    policy = Policy(**_POLICY_DICT)
    decisions = evaluate([_span(SpanLabel.MISC)], policy)
    assert decisions[0].action == Action.PRESERVE
    assert decisions[0].rule_id == "MISC:default_preserve"


def test_long_preserve_span_marked_compressible():
    policy = Policy(**_POLICY_DICT)
    long_text = "x" * 30
    decisions = evaluate([_span(SpanLabel.ORG, start=0, end=30, text=long_text)], policy)
    assert decisions[0].action == Action.PRESERVE
    assert decisions[0].compressible is True


def test_short_preserve_span_not_compressible():
    policy = Policy(**_POLICY_DICT)
    decisions = evaluate([_span(SpanLabel.ORG, start=0, end=5, text="x" * 5)], policy)
    assert decisions[0].compressible is False
