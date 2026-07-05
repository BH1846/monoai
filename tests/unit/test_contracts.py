"""Proof test for core/contracts/ (Step 2). Written before the models exist."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts.audit import AuditRecord
from contracts.policy import Action, PolicyDecision
from contracts.scan import ScanRequest, ScanResult, Verdict
from contracts.spans import DetectedSpan, SpanLabel, SpanSource, TextUnit, TextUnitLocator


def _text_unit() -> TextUnit:
    return TextUnit(
        unit_id="u1",
        role="user",
        text="email me at a@b.com",
        locator=TextUnitLocator(surface="chat_message", path="messages[0].content"),
        turn_index=0,
        direction="input",
    )


def _detected_span() -> DetectedSpan:
    return DetectedSpan(
        unit_id="u1",
        start=11,
        end=19,
        text="a@b.com",
        label=SpanLabel.EMAIL,
        source=SpanSource.REGEX,
        confidence=0.98,
        meta={"negated": False},
    )


def _audit_record() -> AuditRecord:
    return AuditRecord(
        ts=1.0,
        request_id="r1",
        session_id="s1",
        virtual_key_id=None,
        team_id=None,
        event="completed",
        policy_id="default",
        policy_version="sha256:abc",
        detector_versions={"regex": "base_en-v1"},
        pack_versions={"base_en": "base_en-v1"},
        span_counts_by_label={"EMAIL": 1},
        blocked_labels=[],
        redacted_count=1,
        difficulty="simple",
        model_id="m1",
        provider="stub",
        fallback_chain_position=0,
        circuit_state="closed",
        unresolved_tokens=[],
        review_required=False,
        pii_sanitize_ms=1.0,
        router_ms=1.0,
        pii_rehydrate_ms=1.0,
        output_scan_ms=1.0,
        total_ms=3.0,
        usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        cost_usd=0.0,
    )


@pytest.mark.parametrize(
    "factory",
    [_text_unit, _detected_span, _audit_record],
)
def test_round_trip_json(factory) -> None:
    obj = factory()
    cls = type(obj)
    rehydrated = cls.model_validate_json(obj.model_dump_json())
    assert rehydrated == obj


def test_policy_decision_round_trip() -> None:
    decision = PolicyDecision(
        span=_detected_span(),
        action=Action.REVERSIBLE,
        rule_id="EMAIL",
        min_confidence_applied=None,
        compressible=False,
    )
    rehydrated = PolicyDecision.model_validate_json(decision.model_dump_json())
    assert rehydrated == decision


def test_scan_result_round_trip() -> None:
    req = ScanRequest(
        request_id="r1",
        session_id="s1",
        text_units=[_text_unit()],
        locale_hint="en",
        policy_id="default",
        direction="input",
    )
    assert req.locale_hint == "en"

    result = ScanResult(
        request_id="r1",
        session_id="s1",
        verdict=Verdict.ALLOW,
        decisions=[],
        blocked_labels=[],
        policy_id="default",
        policy_version="sha256:abc",
        detector_versions={},
    )
    rehydrated = ScanResult.model_validate_json(result.model_dump_json())
    assert rehydrated == result


def test_audit_record_rejects_missing_policy_version() -> None:
    data = _audit_record().model_dump()
    del data["policy_version"]
    with pytest.raises(ValidationError):
        AuditRecord.model_validate(data)


def test_detected_span_has_no_action_or_classification_field() -> None:
    # Structural guarantee: action-assignment cannot leak back into detection.
    assert "action" not in DetectedSpan.model_fields
    assert "classification" not in DetectedSpan.model_fields
