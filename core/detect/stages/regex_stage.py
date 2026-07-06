"""Regex detection stage: high-precision, high-confidence detectors.

Ported from SENTINEL-2.0/pii_pipeline/rampart/regex.py, minus secrets
detection (split into secrets_stage.py — see DECISIONS.md). Every pattern
is anchored and bounded (no nested quantifiers), so detection is O(n) in
text length: each compiled pattern does a single linear scan via finditer.
"""
from __future__ import annotations

import re

from contracts.spans import SpanLabel, SpanSource

from detect.span import RawSpan

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

_IPV4_RE = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")

_IPV6_RE = re.compile(r"\b(?:[A-Fa-f0-9]{1,4}:){2,7}[A-Fa-f0-9]{1,4}\b")

_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}(?!\d)"
)

_PHONE_INTL_RE = re.compile(
    r"(?<!\d)\+\d{1,3}[\s.\-]?(?:\(\d{1,4}\)[\s.\-]?)?\d{2,4}(?:[\s.\-]?\d{2,4}){1,4}(?!\d)"
)

_SSN_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")

_GOV_ID_DOTTED_RE = re.compile(r"(?<!\d)\d{2,3}\.\d{2}\.\d{4}(?!\d)")

_GOV_ID_PLAIN_RE = re.compile(r"(?<!\d)\d{9}(?!\d)")

_ALNUM_ID_CUE_RE = re.compile(
    r"\b(?:id\s*card|passport|driver'?s?\s*licen[cs]e|licen[cs]e\s*number|"
    r"identification\s*number|national\s*id)\s*(?:number\s*)?(?:is|:)?\s*"
    r"([A-Z]{1,2}\d{5,9}[A-Z]{0,2})",
    re.IGNORECASE,
)

_MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_DATE_NUMERIC_RE = re.compile(r"\b\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b")
_DATE_MONTH_DAY_YEAR_RE = re.compile(
    rf"\b{_MONTH}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}\b", re.IGNORECASE
)
_DATE_DAY_MONTH_YEAR_RE = re.compile(
    rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTH}\.?,?\s+\d{{4}}\b", re.IGNORECASE
)
_TIME_RE = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:[AaPp]\.?[Mm]\.?)?\b")

_USERNAME_HANDLE_RE = re.compile(r"(?<![\w@])@[A-Za-z][A-Za-z0-9_.]{2,29}\b")
_USERNAME_CUE_RE = re.compile(
    r"\b(?:username|user\s*name|handle|login(?:\s+id)?|user\s*id)\s*(?:is|:)\s*"
    r"([A-Za-z0-9][A-Za-z0-9_.\-]{2,29})",
    re.IGNORECASE,
)

_CC_CANDIDATE_RE = re.compile(r"(?<!\d)(?:\d[ \-]?){13,19}(?<=\d)")

_GEOCOORD_RE = re.compile(r"\[-?\d{1,3}\.\d+,\s*-?\d{1,3}\.\d+\]")

_ADDRESS_FIELD_CUE_RE = re.compile(
    r"\b(?:Building|Street|City|State|Post\s*code|Country|Secondary\s*Address)\s*:\s*"
    r"(?:<strong>)?\*{0,2}([^\n<*]{1,50}?)\*{0,2}(?:</strong>)?\s*(?=<|\n|[,.;]|$)",
    re.IGNORECASE,
)

_PERSON_NAME_FIELD_CUE_RE = re.compile(
    r"\b(?:First|Last|Middle|Given|Full)\s*Names?\s*\d{0,2}\s*:\s*"
    r"(?:<strong>)?\*{0,2}[\"']?([^\n<*\"']{1,50}?)[\"']?\*{0,2}(?:</strong>)?\s*(?=<|\n|[,.;\"]|$)",
    re.IGNORECASE,
)

_PERSON_NAME_TAG_CUE_RE = re.compile(r"<name>\s*([^<]{1,80}?)\s*</name>", re.IGNORECASE)

# --- UAE-specific patterns ---
_UAE_EMIRATES_ID_RE = re.compile(r"\b784-?\d{4}-?\d{7}-?\d\b")
_UAE_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+971[\s\-]?|00971[\s\-]?|0)?5[0-9][\s\-]?\d{3}[\s\-]?\d{4}(?!\d)"
)
_UAE_LANDLINE_RE = re.compile(
    r"(?<!\d)(?:\+971[\s\-]?|00971[\s\-]?)[2346789][\s\-]?\d{3}[\s\-]?\d{4}(?!\d)"
    r"|(?<!\d)0[2346789][\s\-]?\d{3}[\s\-]?\d{4}(?!\d)"
)
_UAE_PO_BOX_RE = re.compile(r"\bP\.?\s?O\.?\s?Box\s?\d{1,6}\b", re.IGNORECASE)
_UAE_EMIRATE_NAMES_RE = re.compile(
    r"\b(?:Dubai|Abu Dhabi|Sharjah|Ajman|Fujairah|Ras Al Khaimah|Umm Al Quwain)\b",
    re.IGNORECASE,
)
_UAE_TRADE_LICENSE_RE = re.compile(r"\bCN-?\d{6,7}\b")
_POSTAL_CODE_LIKE_RE = re.compile(r"\b\d{3,6}\b")


def _luhn_ok(digits: str) -> bool:
    total = 0
    parity = len(digits) % 2
    for i, ch in enumerate(digits):
        d = ord(ch) - 48
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


class RegexDetector:
    """Stateless; safe to reuse/share across calls and threads."""

    def detect(self, text: str) -> list[RawSpan]:
        spans: list[RawSpan] = []
        spans.extend(self._detect_credit_cards(text))
        spans.extend(self._detect_ssn(text))
        spans.extend(self._detect_phones(text))
        spans.extend(self._detect_emails(text))
        spans.extend(self._detect_ips(text))
        spans.extend(self._detect_datetimes(text))
        spans.extend(self._detect_usernames(text))
        spans.extend(self._detect_geocoords(text))
        spans.extend(self._detect_address_fields(text))
        spans.extend(self._detect_person_name_fields(text))
        spans.extend(self._detect_uae(text, spans))
        return spans

    def _detect_credit_cards(self, text: str) -> list[RawSpan]:
        spans = []
        for m in _CC_CANDIDATE_RE.finditer(text):
            raw = m.group(0)
            digits = re.sub(r"[ \-]", "", raw)
            if 13 <= len(digits) <= 19 and _luhn_ok(digits):
                spans.append(RawSpan(
                    start=m.start(), end=m.end(), text=raw,
                    label=SpanLabel.CREDIT_CARD, source=SpanSource.REGEX,
                    confidence=0.99, meta={"luhn": True},
                ))
        return spans

    def _detect_ssn(self, text: str) -> list[RawSpan]:
        spans = []
        taken = set()
        for m in _SSN_RE.finditer(text):
            spans.append(RawSpan(
                start=m.start(), end=m.end(), text=m.group(0),
                label=SpanLabel.GOV_ID, source=SpanSource.REGEX,
                confidence=0.9, meta={"format": "ssn-dashed"},
            ))
            taken.add((m.start(), m.end()))
        for m in _GOV_ID_DOTTED_RE.finditer(text):
            if any(a <= m.start() < b or a < m.end() <= b for a, b in taken):
                continue
            spans.append(RawSpan(
                start=m.start(), end=m.end(), text=m.group(0),
                label=SpanLabel.GOV_ID, source=SpanSource.REGEX,
                confidence=0.85, meta={"format": "gov-id-dotted"},
            ))
            taken.add((m.start(), m.end()))
        for m in _GOV_ID_PLAIN_RE.finditer(text):
            if any(a <= m.start() < b or a < m.end() <= b for a, b in taken):
                continue
            spans.append(RawSpan(
                start=m.start(), end=m.end(), text=m.group(0),
                label=SpanLabel.GOV_ID, source=SpanSource.REGEX,
                confidence=0.55, meta={"format": "ssn-plain"},
            ))
        for m in _ALNUM_ID_CUE_RE.finditer(text):
            g_start, g_end = m.start(1), m.end(1)
            if any(a <= g_start < b or a < g_end <= b for a, b in taken):
                continue
            spans.append(RawSpan(
                start=g_start, end=g_end, text=m.group(1),
                label=SpanLabel.GOV_ID, source=SpanSource.REGEX,
                confidence=0.8, meta={"format": "alnum-id-cued"},
            ))
            taken.add((g_start, g_end))
        return spans

    def _detect_phones(self, text: str) -> list[RawSpan]:
        spans = []
        taken = []
        for m in _PHONE_RE.finditer(text):
            digits = re.sub(r"\D", "", m.group(0))
            if len(digits) < 10:
                continue
            spans.append(RawSpan(
                start=m.start(), end=m.end(), text=m.group(0),
                label=SpanLabel.PHONE, source=SpanSource.REGEX,
                confidence=0.93,
            ))
            taken.append((m.start(), m.end()))
        for m in _PHONE_INTL_RE.finditer(text):
            if any(a <= m.start() < b or a < m.end() <= b for a, b in taken):
                continue
            digits = re.sub(r"\D", "", m.group(0))
            if len(digits) < 8:
                continue
            spans.append(RawSpan(
                start=m.start(), end=m.end(), text=m.group(0),
                label=SpanLabel.PHONE, source=SpanSource.REGEX,
                confidence=0.85, meta={"format": "intl"},
            ))
            taken.append((m.start(), m.end()))
        return spans

    def _detect_datetimes(self, text: str) -> list[RawSpan]:
        spans = []
        taken = []
        for pattern, confidence in (
            (_DATE_MONTH_DAY_YEAR_RE, 0.9),
            (_DATE_DAY_MONTH_YEAR_RE, 0.9),
            (_DATE_NUMERIC_RE, 0.85),
        ):
            for m in pattern.finditer(text):
                if any(a <= m.start() < b or a < m.end() <= b for a, b in taken):
                    continue
                spans.append(RawSpan(
                    start=m.start(), end=m.end(), text=m.group(0),
                    label=SpanLabel.DATE_TIME, source=SpanSource.REGEX,
                    confidence=confidence,
                ))
                taken.append((m.start(), m.end()))
        for m in _TIME_RE.finditer(text):
            if any(a <= m.start() < b or a < m.end() <= b for a, b in taken):
                continue
            spans.append(RawSpan(
                start=m.start(), end=m.end(), text=m.group(0),
                label=SpanLabel.DATE_TIME, source=SpanSource.REGEX,
                confidence=0.8,
            ))
            taken.append((m.start(), m.end()))
        return spans

    def _detect_usernames(self, text: str) -> list[RawSpan]:
        spans = []
        taken = []
        for m in _USERNAME_HANDLE_RE.finditer(text):
            spans.append(RawSpan(
                start=m.start(), end=m.end(), text=m.group(0),
                label=SpanLabel.USERNAME, source=SpanSource.REGEX,
                confidence=0.85, meta={"format": "handle"},
            ))
            taken.append((m.start(), m.end()))
        for m in _USERNAME_CUE_RE.finditer(text):
            g_start, g_end = m.start(1), m.end(1)
            if any(a <= g_start < b or a < g_end <= b for a, b in taken):
                continue
            spans.append(RawSpan(
                start=g_start, end=g_end, text=m.group(1),
                label=SpanLabel.USERNAME, source=SpanSource.REGEX,
                confidence=0.75, meta={"format": "cued"},
            ))
            taken.append((g_start, g_end))
        return spans

    def _detect_geocoords(self, text: str) -> list[RawSpan]:
        return [
            RawSpan(start=m.start(), end=m.end(), text=m.group(0),
                    label=SpanLabel.ADDRESS, source=SpanSource.REGEX,
                    confidence=0.85, meta={"format": "geocoord"})
            for m in _GEOCOORD_RE.finditer(text)
        ]

    def _detect_address_fields(self, text: str) -> list[RawSpan]:
        spans = []
        for m in _ADDRESS_FIELD_CUE_RE.finditer(text):
            g_start, g_end = m.start(1), m.end(1)
            if g_end <= g_start:
                continue
            spans.append(RawSpan(
                start=g_start, end=g_end, text=m.group(1),
                label=SpanLabel.ADDRESS, source=SpanSource.REGEX,
                confidence=0.8, meta={"format": "field_cue"},
            ))
        return spans

    def _detect_person_name_fields(self, text: str) -> list[RawSpan]:
        spans = []
        taken = []
        for m in _PERSON_NAME_FIELD_CUE_RE.finditer(text):
            g_start, g_end = m.start(1), m.end(1)
            if g_end <= g_start:
                continue
            spans.append(RawSpan(
                start=g_start, end=g_end, text=m.group(1),
                label=SpanLabel.PERSON, source=SpanSource.REGEX,
                confidence=0.8, meta={"format": "field_cue"},
            ))
            taken.append((g_start, g_end))
        for m in _PERSON_NAME_TAG_CUE_RE.finditer(text):
            g_start, g_end = m.start(1), m.end(1)
            if g_end <= g_start:
                continue
            if any(a <= g_start < b or a < g_end <= b for a, b in taken):
                continue
            spans.append(RawSpan(
                start=g_start, end=g_end, text=m.group(1),
                label=SpanLabel.PERSON, source=SpanSource.REGEX,
                confidence=0.8, meta={"format": "tag_cue"},
            ))
            taken.append((g_start, g_end))
        return spans

    def _detect_uae(self, text: str, existing: list[RawSpan]) -> list[RawSpan]:
        taken = [(s.start, s.end) for s in existing]

        def _overlaps_taken(start: int, end: int) -> bool:
            return any(a <= start < b or a < end <= b for a, b in taken)

        spans: list[RawSpan] = []
        for pattern, label, confidence, fmt in (
            (_UAE_EMIRATES_ID_RE, SpanLabel.GOV_ID, 0.95, "uae_emirates_id"),
            (_UAE_PHONE_RE, SpanLabel.PHONE, 0.85, "uae_mobile"),
            (_UAE_LANDLINE_RE, SpanLabel.PHONE, 0.75, "uae_landline"),
            (_UAE_PO_BOX_RE, SpanLabel.ADDRESS, 0.85, "uae_po_box"),
            (_UAE_TRADE_LICENSE_RE, SpanLabel.GOV_ID, 0.85, "uae_trade_license"),
        ):
            for m in pattern.finditer(text):
                if _overlaps_taken(m.start(), m.end()):
                    continue
                spans.append(RawSpan(
                    start=m.start(), end=m.end(), text=m.group(0),
                    label=label, source=SpanSource.REGEX,
                    confidence=confidence, meta={"format": fmt},
                ))
                taken.append((m.start(), m.end()))

        for m in _UAE_EMIRATE_NAMES_RE.finditer(text):
            if _overlaps_taken(m.start(), m.end()):
                continue
            window_start = max(0, m.start() - 60)
            window_end = min(len(text), m.end() + 60)
            window = text[window_start:window_end]
            if _UAE_PO_BOX_RE.search(window) or _POSTAL_CODE_LIKE_RE.search(window):
                spans.append(RawSpan(
                    start=m.start(), end=m.end(), text=m.group(0),
                    label=SpanLabel.ADDRESS, source=SpanSource.REGEX,
                    confidence=0.65, meta={"format": "uae_emirate_name"},
                ))
                taken.append((m.start(), m.end()))
        return spans

    def _detect_emails(self, text: str) -> list[RawSpan]:
        return [
            RawSpan(start=m.start(), end=m.end(), text=m.group(0),
                    label=SpanLabel.EMAIL, source=SpanSource.REGEX, confidence=0.98)
            for m in _EMAIL_RE.finditer(text)
        ]

    def _detect_ips(self, text: str) -> list[RawSpan]:
        spans = [
            RawSpan(start=m.start(), end=m.end(), text=m.group(0),
                    label=SpanLabel.IP_ADDRESS, source=SpanSource.REGEX, confidence=0.9)
            for m in _IPV4_RE.finditer(text)
        ]
        ipv4_ranges = [(s.start, s.end) for s in spans]
        for m in _IPV6_RE.finditer(text):
            if m.group(0).count(":") < 2:
                continue
            if any(a <= m.start() < b for a, b in ipv4_ranges):
                continue
            spans.append(RawSpan(
                start=m.start(), end=m.end(), text=m.group(0),
                label=SpanLabel.IP_ADDRESS, source=SpanSource.REGEX, confidence=0.85,
            ))
        return spans
