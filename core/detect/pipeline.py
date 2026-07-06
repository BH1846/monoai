"""DetectionPipeline: the single detection pipeline for all surfaces (chat
input/output now; files/MCP tool args reuse this in later phases).

Per TextUnit: normalize -> sentence_split -> (regex + secrets + ner) ->
span_repair -> locked_span_stage (per-sentence, bounds negation scoping) ->
span_merge. Stops there — no action-assignment. That's core/policy's job
(see core/policy/engine.py).

Ported/adapted from SENTINEL-2.0/pii_pipeline/pipeline.py's
`detect_classified_spans` (minus the final `classify_spans` call, and
generalized from "one document" to "one or more TextUnits").
"""
from __future__ import annotations

from typing import Any

from contracts.spans import DetectedSpan, TextUnit

from detect.normalize import map_span, normalize_with_offsets
from detect.sentence_split import Sentence, split_sentences
from detect.span import RawSpan
from detect.stages.locked_span_stage import detect_locked_spans
from detect.stages.ner_stage import DEFAULT_MODEL_PATH, MiniLMNER
from detect.stages.regex_stage import RegexDetector
from detect.stages.secrets_stage import SecretsDetector
from detect.stages.span_merge import merge_spans
from detect.stages.span_repair import repair_spans


def _shift(span: RawSpan, offset: int) -> RawSpan:
    if offset == 0:
        return span
    return RawSpan(
        start=span.start + offset, end=span.end + offset, text=span.text,
        label=span.label, source=span.source, confidence=span.confidence, meta=span.meta,
    )


def _remap_to_original(spans: list[RawSpan], original_text: str, offset_map: list[int]) -> list[RawSpan]:
    out: list[RawSpan] = []
    for span in spans:
        orig_start, orig_end = map_span(offset_map, len(original_text), span.start, span.end)
        if orig_start >= orig_end:
            continue
        out.append(RawSpan(
            start=orig_start, end=orig_end, text=original_text[orig_start:orig_end],
            label=span.label, source=span.source, confidence=span.confidence, meta=span.meta,
        ))
    return out


class DetectionPipeline:
    """Stateless-ish; regex/secrets detectors are stateless, the NER
    backend is loaded once at construction and reused across calls."""

    def __init__(
        self,
        regex_detector: RegexDetector | None = None,
        secrets_detector: SecretsDetector | None = None,
        ner: MiniLMNER | None = None,
        use_onnx_ner: bool = True,
    ) -> None:
        self._regex = regex_detector or RegexDetector()
        self._secrets = secrets_detector or SecretsDetector()
        self._ner = ner or MiniLMNER(model_path=DEFAULT_MODEL_PATH if use_onnx_ner else None)

    def _detect_and_repair(self, text: str, include_ner: bool = True) -> list[RawSpan]:
        # Detect against a normalized view (zero-width chars stripped,
        # full-width unicode folded, letter-spaced obfuscation collapsed)
        # so regex/ner aren't trivially evaded, then project every span
        # back onto the ORIGINAL text's offsets.
        norm_text, offset_map = normalize_with_offsets(text)

        regex_spans = self._regex.detect(norm_text)
        secrets_spans = self._secrets.detect(norm_text)
        # NER needs sentence-level context to be reliable -- on tiny,
        # out-of-context fragments (e.g. a streaming flush window) the
        # model can hallucinate entities from a handful of characters
        # (regression: "mple", a mid-word fragment of "[simple]", was
        # once misclassified as PII this way). Callers scanning small
        # windows (gateway/streaming.py) pass include_ner=False; regex/
        # secrets are anchored patterns and stay reliable at any size.
        ner_spans = self._ner.predict(norm_text) if include_ner else []

        remapped: list[RawSpan] = []
        for span in regex_spans + secrets_spans + ner_spans:
            orig_start, orig_end = map_span(offset_map, len(text), span.start, span.end)
            if orig_start >= orig_end:
                continue
            remapped.append(RawSpan(
                start=orig_start, end=orig_end, text=text[orig_start:orig_end],
                label=span.label, source=span.source, confidence=span.confidence, meta=span.meta,
            ))

        return repair_spans(remapped, text)

    def _locked_spans_for(self, text: str) -> list[RawSpan]:
        norm_text, offset_map = normalize_with_offsets(text)
        sentences: list[Sentence] = split_sentences(norm_text)

        locked: list[RawSpan] = []
        for sentence in sentences:
            for span in detect_locked_spans(sentence.text):
                locked.append(_shift(span, sentence.start))
        return _remap_to_original(locked, text, offset_map)

    def run(
        self,
        text_units: list[TextUnit],
        locale_hint: str = "en",
        policy_ctx: Any = None,
        include_ner: bool = True,
    ) -> list[DetectedSpan]:
        results: list[DetectedSpan] = []
        for unit in text_units:
            detected = self._detect_and_repair(unit.text, include_ner=include_ner)
            locked = self._locked_spans_for(unit.text)
            merged = merge_spans(locked, detected)

            for span in merged:
                results.append(DetectedSpan(
                    unit_id=unit.unit_id,
                    start=span.start,
                    end=span.end,
                    text=span.text,
                    label=span.label,
                    source=span.source,
                    confidence=span.confidence,
                    meta=span.meta,
                ))
        return results
