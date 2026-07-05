"""Policy engine: maps label -> action per the loaded policy. Detectors
(core/detect) only ever report label + confidence + meta hints; this is
the only place action-assignment happens (see DECISIONS.md).
"""
from __future__ import annotations

from contracts.policy import Action, PolicyDecision
from contracts.spans import DetectedSpan
from policy.schema import Policy


def evaluate(spans: list[DetectedSpan], policy: Policy) -> list[PolicyDecision]:
    decisions: list[PolicyDecision] = []

    for span in spans:
        rule = policy.rules.get(span.label)
        min_confidence_applied: float | None = None

        if rule is None:
            action = Action.PRESERVE
            rule_id = f"{span.label.value}:default_preserve"
        else:
            action = rule.action
            rule_id = span.label.value
            if rule.min_confidence is not None:
                min_confidence_applied = rule.min_confidence
                if span.confidence < rule.min_confidence and rule.below_min_confidence_action is not None:
                    action = rule.below_min_confidence_action
                    rule_id = f"{span.label.value}:below_min_confidence"

        override = policy.overrides.get("locked_span_negation")
        if override is not None and override.when_meta_negated and span.meta.get("negated") is True:
            action = override.action
            rule_id = "locked_span_negation"

        compressible = action == Action.PRESERVE and (span.end - span.start) > policy.compressible_length_threshold

        decisions.append(PolicyDecision(
            span=span,
            action=action,
            rule_id=rule_id,
            min_confidence_applied=min_confidence_applied,
            compressible=compressible,
        ))

    return decisions
