"""locked_span_stage: rule-based negation + syntactic-anchor detection.

Ported from SENTINEL-2.0/pii_pipeline/locked_spans.py, with one behavior
change: this stage no longer decides the action override itself. It only
attaches `span.meta["negated"] = True` on a negated anchor; the actual
PRESERVE override is applied by core/policy/engine.py's
`overrides.locked_span_negation` rule (see DECISIONS.md — classification
moves out of detectors into policy).

This stage does two things, both scoped to explicit "my/the <type> is/was
<value>" ownership anchors:

1. Negation: "not my email is X", "my SSN isn't X" -> meta["negated"]=True.
2. Positive syntactic anchors: "my email is X" with no negation -> re-emit
   the span with source=LOCKED and boosted confidence so it reliably wins
   span_merge over a possibly-lower-confidence/partial regex/ner guess.

Output spans always win over regex/ner spans on overlap (enforced in
span_merge, not here).

Pure regex, single finditer pass per entity type -> O(n) in text length.
"""
from __future__ import annotations

import re

from contracts.spans import SpanLabel, SpanSource

from detect.span import RawSpan
from detect.stages.regex_stage import (
    _CC_CANDIDATE_RE,
    _DATE_DAY_MONTH_YEAR_RE,
    _DATE_MONTH_DAY_YEAR_RE,
    _DATE_NUMERIC_RE,
    _EMAIL_RE,
    _PHONE_RE,
    _SSN_RE,
    _TIME_RE,
    _luhn_ok,
)

_NEGATION_PRE = r"(?:not|never|no longer|isn'?t|wasn'?t|aren'?t|doesn'?t|didn'?t)"
_COPULA = r"(?:is|was|are|isn'?t|wasn'?t|aren'?t)"
_POSSESSIVE = r"(?:my|the|his|her|their|our|user'?s)"
_NEG_POST = r"(?:\w+\s+){0,2}not\s+"
_ZONE_END = r"(?=[.!?](?:\s|$)|[;—–]|\n|$)"

_NAME_VALUE_RE = re.compile(r"[A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+){0,2}")
_ADDRESS_VALUE_RE = re.compile(r"\S(?:.*\S)?")
_USERNAME_VALUE_RE = re.compile(r"@?[A-Za-z0-9][A-Za-z0-9_.\-]{2,29}")
_DATETIME_VALUE_RE = re.compile(
    "|".join(p.pattern for p in (
        _DATE_MONTH_DAY_YEAR_RE, _DATE_DAY_MONTH_YEAR_RE, _DATE_NUMERIC_RE, _TIME_RE,
    )),
    re.IGNORECASE,
)


class _EntityAnchor:
    def __init__(self, label: SpanLabel, type_words: str, value_re: re.Pattern,
                 value_validator=None, pattern: str | None = None):
        self.label = label
        self.anchor_re = re.compile(
            pattern if pattern is not None else (
                rf"\b(?P<neg_pre>{_NEGATION_PRE}\s+)?{_POSSESSIVE}\s+(?:{type_words})\s+"
                rf"(?P<copula>{_COPULA})\s+(?P<neg_post>{_NEG_POST})?"
                rf"(?P<value_zone>.{{1,80}}?){_ZONE_END}"
            ),
            re.IGNORECASE,
        )
        self.value_re = value_re
        self.value_validator = value_validator


_ADDRESS_VERB_PATTERN = (
    rf"\b(?P<neg_pre>(?:not|never|no longer|don'?t|doesn'?t|didn'?t)\s+)?"
    rf"(?:live[sd]?|reside[sd]?)(?P<copula>)\s+at\s+(?P<neg_post>)"
    rf"(?P<value_zone>.{{1,80}}?){_ZONE_END}"
)

_ANCHORS = [
    _EntityAnchor(SpanLabel.EMAIL, r"e-?mail(?:\s+address)?", _EMAIL_RE),
    _EntityAnchor(SpanLabel.PHONE, r"(?:phone|cell|mobile)(?:\s+number)?|number", _PHONE_RE),
    _EntityAnchor(SpanLabel.GOV_ID, r"ssn|social security(?:\s+number)?|national id|passport(?:\s+number)?", _SSN_RE),
    _EntityAnchor(SpanLabel.CREDIT_CARD, r"(?:credit\s+card|card)(?:\s+number)?",
                  _CC_CANDIDATE_RE,
                  value_validator=lambda raw: _luhn_ok(re.sub(r"[ \-]", "", raw))),
    _EntityAnchor(SpanLabel.PERSON, r"name", _NAME_VALUE_RE),
    _EntityAnchor(SpanLabel.ADDRESS, r"address", _ADDRESS_VALUE_RE),
    _EntityAnchor(SpanLabel.ADDRESS, "", _ADDRESS_VALUE_RE, pattern=_ADDRESS_VERB_PATTERN),
    _EntityAnchor(SpanLabel.USERNAME, r"username|handle|user\s*name|login(?:\s+id)?", _USERNAME_VALUE_RE),
    _EntityAnchor(SpanLabel.DATE_TIME, r"date\s+of\s+birth|birth\s*date|birthday|dob", _DATETIME_VALUE_RE),
]


def _is_negated(match: re.Match) -> bool:
    if match.group("neg_pre") or match.group("neg_post"):
        return True
    return "n't" in match.group("copula").lower()


def _locate_value(anchor: _EntityAnchor, zone_start: int, zone_text: str) -> RawSpan | None:
    value_match = anchor.value_re.search(zone_text)
    if not value_match:
        return None
    raw = value_match.group(0)
    if anchor.value_validator and not anchor.value_validator(raw):
        return None
    start = zone_start + value_match.start()
    end = zone_start + value_match.end()
    return RawSpan(start=start, end=end, text=raw, label=anchor.label, source=SpanSource.LOCKED)


def detect_locked_spans(text: str) -> list[RawSpan]:
    spans: list[RawSpan] = []
    for anchor in _ANCHORS:
        for match in anchor.anchor_re.finditer(text):
            zone_start = match.start("value_zone")
            zone_text = match.group("value_zone")
            span = _locate_value(anchor, zone_start, zone_text)
            if span is None:
                continue
            negated = _is_negated(match)
            span.confidence = 0.9 if negated else 0.95
            span.meta = {"anchor": match.group(0).strip(), "negated": negated}
            spans.append(span)
    return sorted(spans, key=lambda s: s.start)
