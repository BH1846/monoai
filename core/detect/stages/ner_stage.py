"""NER detection stage: catches names, addresses, orgs, and other entities
the regex stage structurally cannot (no fixed format to anchor on).

Ported from SENTINEL-2.0/pii_pipeline/rampart/minilm.py. `OnnxMiniLMBackend`
wraps a real quantized (int8) DistilBERT token-classification ONNX model;
`MiniLMNER` falls back to a deterministic rule-based tagger
(`RuleBasedNERBackend`) if the ONNX model/runtime aren't available. Both
backends implement the same `NERBackend.predict(text)` interface. Stays
in-process in Phase 1 (see ner-sidecar/README.md — the HTTP/gRPC boundary
is Phase 2).
"""
from __future__ import annotations

import os
import re
from typing import Protocol

from contracts.spans import SpanLabel, SpanSource

from detect.span import RawSpan


class NERBackend(Protocol):
    def predict(self, text: str) -> list[RawSpan]:
        ...


# ---------------------------------------------------------------------------
# ONNX (real quantized MiniLM) backend — used when a model is actually present.
# ---------------------------------------------------------------------------

class OnnxMiniLMBackend:
    """Thin wrapper around an int8-quantized DistilBERT token-classification
    model exported to ONNX. Expects a HuggingFace-style `tokenizer.json`
    next to the `.onnx` file for a fast WordPiece/BPE tokenizer.

    Raises on construction if onnxruntime or the model files aren't
    available, so `MiniLMNER` can catch that and fall back cleanly.
    """

    # Full BIO label set exposed by Isotonic/distilbert_finetuned_ai4privacy_v2
    # (from its config.json id2label, 111 entries) -- must match the
    # exported ONNX model's output order exactly.
    ID2LABEL = {
        0: "O", 1: "B-PHONEIMEI", 2: "I-PHONEIMEI", 3: "B-JOBAREA",
        4: "B-FIRSTNAME", 5: "I-FIRSTNAME", 6: "B-VEHICLEVIN", 7: "I-VEHICLEVIN",
        8: "B-AGE", 9: "B-GENDER", 10: "I-GENDER", 11: "B-HEIGHT", 12: "I-HEIGHT",
        13: "B-BUILDINGNUMBER", 14: "I-BUILDINGNUMBER", 15: "B-MASKEDNUMBER",
        16: "I-MASKEDNUMBER", 17: "B-PASSWORD", 18: "I-PASSWORD", 19: "B-DOB",
        20: "I-DOB", 21: "B-IPV6", 22: "I-IPV6", 23: "B-NEARBYGPSCOORDINATE",
        24: "I-NEARBYGPSCOORDINATE", 25: "B-USERAGENT", 26: "I-USERAGENT",
        27: "B-TIME", 28: "I-TIME", 29: "B-JOBTITLE", 30: "I-JOBTITLE",
        31: "B-COUNTY", 32: "B-EMAIL", 33: "I-EMAIL", 34: "B-ACCOUNTNUMBER",
        35: "I-ACCOUNTNUMBER", 36: "B-PIN", 37: "I-PIN", 38: "B-EYECOLOR",
        39: "I-EYECOLOR", 40: "B-LASTNAME", 41: "I-LASTNAME", 42: "I-JOBAREA",
        43: "B-IPV4", 44: "I-IPV4", 45: "B-DATE", 46: "I-DATE", 47: "B-STREET",
        48: "I-STREET", 49: "B-CITY", 50: "I-CITY", 51: "B-PREFIX",
        52: "I-PREFIX", 53: "B-CREDITCARDISSUER", 54: "B-CREDITCARDNUMBER",
        55: "I-CREDITCARDNUMBER", 56: "I-CREDITCARDISSUER", 57: "B-MIDDLENAME",
        58: "B-STATE", 59: "I-STATE", 60: "B-VEHICLEVRM", 61: "I-VEHICLEVRM",
        62: "B-ORDINALDIRECTION", 63: "B-SEX", 64: "B-JOBTYPE", 65: "I-JOBTYPE",
        66: "B-CURRENCYCODE", 67: "I-CURRENCYCODE", 68: "B-CURRENCYSYMBOL",
        69: "I-AMOUNT", 70: "B-ACCOUNTNAME", 71: "I-ACCOUNTNAME",
        72: "B-BITCOINADDRESS", 73: "I-BITCOINADDRESS", 74: "B-LITECOINADDRESS",
        75: "I-LITECOINADDRESS", 76: "B-PHONENUMBER", 77: "I-PHONENUMBER",
        78: "B-MAC", 79: "I-MAC", 80: "B-CURRENCY", 81: "B-IBAN", 82: "I-IBAN",
        83: "B-COMPANYNAME", 84: "I-COMPANYNAME", 85: "B-CURRENCYNAME",
        86: "I-CURRENCYNAME", 87: "I-CURRENCYSYMBOL", 88: "B-ZIPCODE",
        89: "I-ZIPCODE", 90: "B-SSN", 91: "I-SSN", 92: "B-AMOUNT",
        93: "I-CURRENCY", 94: "B-URL", 95: "I-URL", 96: "B-IP", 97: "I-IP",
        98: "B-SECONDARYADDRESS", 99: "I-SECONDARYADDRESS", 100: "B-USERNAME",
        101: "I-USERNAME", 102: "B-ETHEREUMADDRESS", 103: "I-ETHEREUMADDRESS",
        104: "B-CREDITCARDCVV", 105: "I-CREDITCARDCVV", 106: "I-COUNTY",
        107: "I-AGE", 108: "I-MIDDLENAME", 109: "B-BIC", 110: "I-BIC",
    }

    # Raw ai4Privacy label -> the SpanLabel it corresponds to, restricted to
    # the five NER-detectable types that regex_stage can't structurally
    # cover. Everything else the model tags (EMAIL, PHONE, dates, card
    # numbers, ...) is dropped since regex_stage already detects those
    # formats with tighter, format-anchored precision.
    RAW_LABEL_TO_SPANLABEL = {
        "FIRSTNAME": SpanLabel.PERSON, "LASTNAME": SpanLabel.PERSON,
        "MIDDLENAME": SpanLabel.PERSON,
        "PREFIX": SpanLabel.TITLE, "JOBTITLE": SpanLabel.TITLE,
        "JOBAREA": SpanLabel.TITLE, "JOBTYPE": SpanLabel.TITLE,
        "STREET": SpanLabel.ADDRESS, "CITY": SpanLabel.ADDRESS,
        "STATE": SpanLabel.ADDRESS, "COUNTY": SpanLabel.ADDRESS,
        "ZIPCODE": SpanLabel.ADDRESS, "BUILDINGNUMBER": SpanLabel.ADDRESS,
        "SECONDARYADDRESS": SpanLabel.ADDRESS,
        "NEARBYGPSCOORDINATE": SpanLabel.ADDRESS,
        "ORDINALDIRECTION": SpanLabel.ADDRESS,
        "COMPANYNAME": SpanLabel.ORG, "CREDITCARDISSUER": SpanLabel.ORG,
        "AGE": SpanLabel.DEMOGRAPHIC, "GENDER": SpanLabel.DEMOGRAPHIC,
        "SEX": SpanLabel.DEMOGRAPHIC, "EYECOLOR": SpanLabel.DEMOGRAPHIC,
        "HEIGHT": SpanLabel.DEMOGRAPHIC,
    }

    def __init__(self, model_path: str):
        import onnxruntime as ort  # noqa: F401  (import error -> fallback)
        from tokenizers import Tokenizer  # noqa: F401

        if not os.path.isfile(model_path):
            raise FileNotFoundError(model_path)
        tokenizer_path = os.path.join(os.path.dirname(model_path), "tokenizer.json")
        if not os.path.isfile(tokenizer_path):
            raise FileNotFoundError(tokenizer_path)

        self._session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self._tokenizer = Tokenizer.from_file(tokenizer_path)

    def predict(self, text: str) -> list[RawSpan]:
        import numpy as np

        encoding = self._tokenizer.encode(text)
        input_ids = np.array([encoding.ids], dtype=np.int64)
        attention_mask = np.array([encoding.attention_mask], dtype=np.int64)
        outputs = self._session.run(None, {"input_ids": input_ids, "attention_mask": attention_mask})
        logits = outputs[0][0]  # (seq_len, num_labels)
        label_ids = logits.argmax(axis=-1)

        spans: list[RawSpan] = []
        current_label = None
        current_start = None
        current_end = None
        current_conf = 0.0
        count = 0

        def flush():
            nonlocal current_label, current_start, current_end
            span_label = self.RAW_LABEL_TO_SPANLABEL.get(current_label) if current_label else None
            if span_label is not None and current_start is not None:
                spans.append(RawSpan(
                    start=current_start, end=current_end,
                    text=text[current_start:current_end],
                    label=span_label,
                    source=SpanSource.NER,
                    confidence=current_conf / max(count, 1),
                    meta={"raw_label": current_label},
                ))
            current_label = None
            current_start = None
            current_end = None

        for tok_idx, label_id in enumerate(label_ids):
            offset = encoding.offsets[tok_idx]
            if offset == (0, 0):
                continue
            bio_label = self.ID2LABEL.get(int(label_id), "O")
            if bio_label == "O":
                flush()
                continue
            prefix, _, ent_type = bio_label.partition("-")
            if prefix == "B" or ent_type != current_label:
                flush()
                current_label = ent_type
                current_start = offset[0]
                current_conf = 0.0
                count = 0
            current_end = offset[1]
            row = logits[tok_idx]
            softmax_max = float(np.exp(row - row.max()).max() / np.exp(row - row.max()).sum())
            current_conf += softmax_max
            count += 1
        flush()
        return spans


# ---------------------------------------------------------------------------
# Rule-based fallback backend — pure stdlib, deterministic, O(n).
# ---------------------------------------------------------------------------

_SENTENCE_START_STOP = {
    "i", "im", "the", "my", "hi", "hello", "hey", "dear", "please", "thanks",
    "thank", "call", "is", "it", "this", "that", "you", "your", "we", "our",
}

_TITLE = r"(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr)\.?"
_NAME_CUE_RE = re.compile(
    r"\b(?i:my name is|i am|i'm|this is|call me|contact|reach out to|attn:?|"
    rf"signed|regards,?|from|{_TITLE})\s+"
    rf"(?:{_TITLE}\s+)?"
    r"([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+){0,2})"
)

_CAPWORD_SEQ_RE = re.compile(
    r"(?<![.!?]\s)(?<!^)\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b"
)

_FIELD_LABEL_SUFFIX_RE = re.compile(r"^\s{0,2}:")

_STREET_SUFFIXES = (
    r"Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Lane|Ln|Drive|Dr|Court|Ct|"
    r"Way|Place|Pl|Terrace|Circle|Cir|Square|Sq|Highway|Hwy"
)
_ADDRESS_RE = re.compile(
    rf"\b(?:\d{{1,6}},?\s+)?[A-Z][A-Za-z0-9'.\-]*(?:\s+[A-Z][A-Za-z0-9'.\-]*){{0,4}}\s+"
    rf"(?:{_STREET_SUFFIXES})\b\.?"
    rf"(?:,?\s+[A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+){{0,2}})?"
    rf"(?:,?\s+[A-Z]{{2,3}})?"
    rf"(?:,?\s+\d{{5}}(?:-\d{{4}})?)?"
    rf"(?:,?\s+[A-Z]{{1,2}}\d[A-Z0-9]?\s?\d[A-Z]{{2}})?",
)

_ORG_SUFFIXES = (
    r"Inc\.?|LLC|L\.L\.C\.|Corp\.?|Corporation|Ltd\.?|Co\.|Company|Group|"
    r"Technologies|Labs|Partners|Holdings|Industries"
)
_ORG_RE = re.compile(
    rf"\b([A-Z][A-Za-z0-9&'\-]*(?:\s+[A-Z][A-Za-z0-9&'\-]*){{0,4}}\s+"
    rf"(?:{_ORG_SUFFIXES}))\b"
)

_DEMOGRAPHIC_TERMS = (
    r"Male|Female|Non-binary|Nonbinary|Genderqueer|Genderfluid|Agender|Bigender|"
    r"Transgender|Trans(?:\s+(?:[Mm]an|[Ww]oman))?|Cisgender|Intersex|Two-Spirit"
)
_DEMOGRAPHIC_RE = re.compile(rf"\b(?:{_DEMOGRAPHIC_TERMS})\b")

_TITLE_TERMS = (
    r"Doctor|Professor|Manager|Director|Engineer|Analyst|Consultant|Officer|"
    r"President|Attorney|Barrister|Solicitor|Nurse|Teacher|Accountant|Architect|"
    r"Pharmacist|Surgeon|Physician|Dentist|Paralegal|Auditor|Technician|Supervisor|"
    r"Administrator|Coordinator|Specialist|Executive|Chairman|Chairwoman|Chairperson|"
    r"CEO|CFO|CTO|COO|Editor|Journalist|Reporter|Scientist|Researcher|Sergeant|"
    r"Captain|Lieutenant|Colonel|General|Judge|Magistrate"
)
_TITLE_RE = re.compile(rf"\b(?:{_TITLE_TERMS})\b")

_CARD_ISSUER_TERMS = (
    r"Mastercard|American Express|Diners Club International|"
    r"Diners Club|JCB|UnionPay|China T-Union|RuPay|Interac"
)
_CARD_ISSUER_RE = re.compile(rf"\b(?:{_CARD_ISSUER_TERMS})\b")


class RuleBasedNERBackend:
    """Deterministic heuristic tagger used when no real MiniLM model is
    configured. Confidence scores are heuristic, not calibrated probabilities."""

    def predict(self, text: str) -> list[RawSpan]:
        spans: list[RawSpan] = []
        spans.extend(self._persons(text))
        spans.extend(self._addresses(text))
        spans.extend(self._orgs(text))
        spans.extend(self._card_issuers(text))
        spans.extend(self._demographics(text))
        spans.extend(self._titles(text))
        return spans

    def _persons(self, text: str) -> list[RawSpan]:
        spans = []
        cued = []
        for m in _NAME_CUE_RE.finditer(text):
            g = m.group(1)
            start = m.start(1)
            end = m.end(1)
            spans.append(RawSpan(
                start=start, end=end, text=g, label=SpanLabel.PERSON,
                source=SpanSource.NER, confidence=0.88,
                meta={"heuristic": "name_cue"},
            ))
            cued.append((start, end))

        for m in _CAPWORD_SEQ_RE.finditer(text):
            g = m.group(1)
            start, end = m.start(1), m.end(1)
            if any(a <= start < b for a, b in cued):
                continue
            first_word = g.split()[0].lower()
            if first_word in _SENTENCE_START_STOP:
                continue
            if re.search(rf"\b(?:{_ORG_SUFFIXES})\b", g):
                continue
            if _FIELD_LABEL_SUFFIX_RE.match(text[end:end + 4]):
                continue
            spans.append(RawSpan(
                start=start, end=end, text=g, label=SpanLabel.PERSON,
                source=SpanSource.NER, confidence=0.55,
                meta={"heuristic": "capword_seq"},
            ))
        return spans

    def _addresses(self, text: str) -> list[RawSpan]:
        return [
            RawSpan(start=m.start(), end=m.end(), text=m.group(0),
                    label=SpanLabel.ADDRESS, source=SpanSource.NER,
                    confidence=0.8, meta={"heuristic": "street_pattern"})
            for m in _ADDRESS_RE.finditer(text)
        ]

    def _orgs(self, text: str) -> list[RawSpan]:
        return [
            RawSpan(start=m.start(1), end=m.end(1), text=m.group(1),
                    label=SpanLabel.ORG, source=SpanSource.NER,
                    confidence=0.75, meta={"heuristic": "org_suffix"})
            for m in _ORG_RE.finditer(text)
        ]

    def _card_issuers(self, text: str) -> list[RawSpan]:
        return [
            RawSpan(start=m.start(), end=m.end(), text=m.group(0),
                    label=SpanLabel.ORG, source=SpanSource.NER,
                    confidence=0.8, meta={"heuristic": "card_issuer_vocab"})
            for m in _CARD_ISSUER_RE.finditer(text)
        ]

    def _demographics(self, text: str) -> list[RawSpan]:
        return [
            RawSpan(start=m.start(), end=m.end(), text=m.group(0),
                    label=SpanLabel.DEMOGRAPHIC, source=SpanSource.NER,
                    confidence=0.7, meta={"heuristic": "demographic_vocab"})
            for m in _DEMOGRAPHIC_RE.finditer(text)
        ]

    def _titles(self, text: str) -> list[RawSpan]:
        return [
            RawSpan(start=m.start(), end=m.end(), text=m.group(0),
                    label=SpanLabel.TITLE, source=SpanSource.NER,
                    confidence=0.65, meta={"heuristic": "title_vocab"})
            for m in _TITLE_RE.finditer(text)
        ]


DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "packs", "base_en", "models",
    "ner_distilbert_ai4privacy_int8.onnx",
)


class MiniLMNER:
    """Public entry point used by the rest of the pipeline. Selects a real
    ONNX backend if `model_path` resolves to an actual model, otherwise uses
    the rule-based fallback so the pipeline stays fully functional offline.
    """

    def __init__(self, model_path: str | None = None):
        self.backend_name = "rule_based"
        self._backend: NERBackend = RuleBasedNERBackend()

        if model_path:
            try:
                self._backend = OnnxMiniLMBackend(model_path)
                self.backend_name = "onnx_minilm_int8"
            except Exception:  # noqa: BLE001 - deliberate broad fallback
                pass

    def predict(self, text: str) -> list[RawSpan]:
        return self._backend.predict(text)
