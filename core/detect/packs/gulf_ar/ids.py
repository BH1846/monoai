"""Gulf-region government ID detectors (Phase 4): Emirates ID, Iqama,
Saudi National ID, Qatar QID, Bahrain CPR, Kuwait Civil ID, Oman civil
number.

Confidence is NOT a flat per-format constant -- it starts from a
structural-match baseline and is adjusted by two independent signals:
  1. checksum result (True: boosted: False: penalized; None: format has
     no publicly documented official checksum, left alone)
  2. a nearby Arabic ID-related cue word (morphology.has_id_cue_nearby)

See DECISIONS.md for exactly which checksums below are confirmed
against a public reference implementation vs. best-effort/unofficial
vs. absent entirely -- this module does NOT invent a checksum where a
reliable public spec couldn't be found (Qatar QID, Bahrain CPR, Oman
civil number are structural-pattern-only).
"""
from __future__ import annotations

import re
from typing import Callable, Optional

from contracts.spans import SpanLabel, SpanSource

from detect.packs.gulf_ar.morphology import has_id_cue_nearby
from detect.span import RawSpan

# Arabic-Indic and Eastern Arabic-Indic (Persian/Urdu) digits fold to
# ASCII 1:1 -- same string length, same character positions -- so
# spans found against the folded copy need no offset remapping at all;
# `RawSpan.text` is sliced from the ORIGINAL text at the same (start,
# end) to preserve whatever digit script the source actually used.
_ARABIC_INDIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_EASTERN_ARABIC_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_DIGIT_FOLD_MAP = {ch: str(i) for i, ch in enumerate(_ARABIC_INDIC_DIGITS)}
_DIGIT_FOLD_MAP.update({ch: str(i) for i, ch in enumerate(_EASTERN_ARABIC_DIGITS)})
_DIGIT_TRANSLATE = str.maketrans(_DIGIT_FOLD_MAP)


def fold_digits(text: str) -> str:
    return text.translate(_DIGIT_TRANSLATE)


def _saudi_style_checksum(digits: str) -> bool:
    """Saudi National ID / Iqama (10 digits, leading '1' or '2').
    Confirmed against a widely-used open-source reference
    implementation (github.com/alhazmy13/Saudi-ID-Validator): double
    each even-indexed (0-indexed) digit, sum-of-digits on overflow
    (equivalent to subtracting 9), valid iff the total is divisible by
    10. This is the standard Luhn doubling rule, just applied
    starting from index 0 rather than from the check digit."""
    if len(digits) != 10 or not digits.isdigit() or digits[0] not in ("1", "2"):
        return False
    checksum = 0
    for i, ch in enumerate(digits):
        n = int(ch)
        if i % 2 == 0:
            doubled = n * 2
            checksum += doubled if doubled < 10 else doubled - 9
        else:
            checksum += n
    return checksum % 10 == 0


def _kuwait_civil_id_checksum(digits: str) -> bool:
    """Kuwait Civil ID (12 digits). Confirmed weighted mod-11 checksum:
    weights (2,1,6,3,7,9,10,5,8,4,2) applied to the first 11 digits;
    check digit = 11 - (weighted sum mod 11). The two results that
    can't map onto a single digit (11-0=11, 11-1=10) are treated as
    "does not validate" rather than guessed at."""
    if len(digits) != 12 or not digits.isdigit():
        return False
    weights = (2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
    total = sum(int(d) * w for d, w in zip(digits[:11], weights))
    expected = 11 - (total % 11)
    if expected >= 10:
        return False
    return expected == int(digits[11])


def _uae_eid_luhn(digits: str) -> Optional[bool]:
    """UAE Emirates ID (15 digits, 784-prefixed). UNOFFICIAL: a
    community-reverse-engineered Luhn variant, never confirmed by the
    UAE government, and documented by its own authors as rejecting
    some real, valid Emirates IDs (see DECISIONS.md). Used only to
    nudge confidence, never as a hard accept/reject gate -- returns
    None (rather than False) on malformed input so callers can tell
    "didn't check" apart from "checked and failed"."""
    if len(digits) != 15 or not digits.isdigit():
        return None
    check_digit = int(digits[-1])
    total = 0
    double = True
    for ch in reversed(digits[:-1]):
        n = int(ch)
        if double:
            n *= 2
            if n > 9:
                n -= 9
        total += n
        double = not double
    return ((total * 9) % 10) == check_digit


# (compiled pattern, checksum fn or None, gulf_id_type, structural base confidence)
_ID_ENGINES: tuple[tuple[re.Pattern, Optional[Callable[[str], Optional[bool]]], str, float], ...] = (
    (re.compile(r"\b784-?\d{4}-?\d{7}-?\d\b"), _uae_eid_luhn, "uae_emirates_id", 0.9),
    (re.compile(r"\b2\d{9}\b"), _saudi_style_checksum, "sa_iqama", 0.55),
    (re.compile(r"\b1\d{9}\b"), _saudi_style_checksum, "sa_national_id", 0.55),
    (re.compile(r"\b[23]\d{10}\b"), None, "qa_qid", 0.5),
    (re.compile(r"\b\d{2}(?:0[1-9]|1[0-2])\d{5}\b"), None, "bh_cpr", 0.4),
    (re.compile(r"\b[23]\d{11}\b"), _kuwait_civil_id_checksum, "kw_civil_id", 0.55),
    (re.compile(r"\b\d{8}\b"), None, "om_civil_number", 0.3),
)


class GulfArIdDetector:
    """Stateless; safe to reuse/share across calls and threads (same
    contract as core/detect/stages/regex_stage.py's RegexDetector)."""

    def detect(self, text: str) -> list[RawSpan]:
        folded = fold_digits(text)
        taken: list[tuple[int, int]] = []
        spans: list[RawSpan] = []

        for pattern, checker, id_type, base_confidence in _ID_ENGINES:
            for m in pattern.finditer(folded):
                start, end = m.start(), m.end()
                if any(a <= start < b or a < end <= b for a, b in taken):
                    continue  # a higher-specificity pattern (e.g. 15-digit EID) already claimed this range

                digits = re.sub(r"[\s\-]", "", m.group(0))
                checksum_valid = checker(digits) if checker is not None else None

                confidence = base_confidence
                if checksum_valid is True:
                    confidence = min(0.99, base_confidence + 0.4)
                elif checksum_valid is False:
                    confidence = max(0.15, base_confidence - 0.25)
                if has_id_cue_nearby(text, start, end):
                    confidence = min(0.99, confidence + 0.15)

                spans.append(RawSpan(
                    start=start, end=end, text=text[start:end],
                    label=SpanLabel.GOV_ID, source=SpanSource.REGEX, confidence=confidence,
                    meta={"gulf_id_type": id_type, "checksum_valid": checksum_valid},
                ))
                taken.append((start, end))

        return spans
