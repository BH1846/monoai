"""Shared scan logic (G16): extract -> core/detect -> core/policy ->
masked report.

No vault involvement by design: file scanning is a standalone
governance surface (a document dropped on an admin/compliance
endpoint), not a chat session with a rehydration story. REVERSIBLE and
BLOCK spans are both masked in the report -- there's no vault-backed
"put it back later" here, only "here's what was found and where."
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from contracts.spans import TextUnit, TextUnitLocator
from detect.pipeline import DetectionPipeline
from policy.engine import evaluate
from policy.schema import Policy

from extract import extract_units


@dataclass
class FileFinding:
    location: str
    label: str
    action: str
    start: int
    end: int


@dataclass
class FileScanResult:
    filename: str
    kind: str
    policy_id: str
    units_scanned: int
    span_counts_by_label: dict[str, int]
    blocked: bool
    findings: list[FileFinding] = field(default_factory=list)
    masked_units: dict[str, str] = field(default_factory=dict)


def scan_file(data: bytes, filename: str, kind: str, pipeline: DetectionPipeline, policy: Policy) -> FileScanResult:
    raw_units = extract_units(data, kind)

    text_units: list[TextUnit] = []
    location_by_unit_id: dict[str, str] = {}
    text_by_unit_id: dict[str, str] = {}
    for i, (location, text) in enumerate(raw_units):
        unit_id = f"u{i}"
        text_units.append(TextUnit(
            unit_id=unit_id, role="user", text=text,
            locator=TextUnitLocator(surface="file_field", path=f"{filename}#{location}"),
            turn_index=i, direction="input",
        ))
        location_by_unit_id[unit_id] = location
        text_by_unit_id[unit_id] = text

    spans = pipeline.run(text_units, locale_hint=policy.locale_hint, policy_ctx=policy)
    decisions = evaluate(spans, policy)

    span_counts: dict[str, int] = {}
    findings: list[FileFinding] = []
    blocked = False
    decisions_by_unit: dict[str, list[Any]] = {}
    for d in decisions:
        decisions_by_unit.setdefault(d.span.unit_id, []).append(d)
        span_counts[d.span.label.value] = span_counts.get(d.span.label.value, 0) + 1
        if d.action.value == "BLOCK":
            blocked = True
        findings.append(FileFinding(
            location=location_by_unit_id[d.span.unit_id], label=d.span.label.value,
            action=d.action.value, start=d.span.start, end=d.span.end,
        ))

    masked_units: dict[str, str] = {}
    for unit in text_units:
        text = text_by_unit_id[unit.unit_id]
        unit_decisions = sorted(decisions_by_unit.get(unit.unit_id, []), key=lambda d: d.span.start)
        out: list[str] = []
        last_end = 0
        for d in unit_decisions:
            span = d.span
            if span.start < last_end:
                continue
            out.append(text[last_end:span.start])
            if d.action.value in ("BLOCK", "REVERSIBLE"):
                out.append(f"[REDACTED_{span.label.value}]")
            else:
                out.append(span.text)
            last_end = span.end
        out.append(text[last_end:])
        masked_units[location_by_unit_id[unit.unit_id]] = "".join(out)

    return FileScanResult(
        filename=filename, kind=kind, policy_id=policy.policy_id, units_scanned=len(text_units),
        span_counts_by_label=span_counts, blocked=blocked, findings=findings, masked_units=masked_units,
    )
