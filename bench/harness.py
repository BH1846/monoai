#!/usr/bin/env python3
"""bench/harness.py (G15, Phase 4): synthetic-payload evaluation harness
comparing MonoAI Gateway's real detection pipeline against four MOCK
baseline runners loosely modeled on the public positioning of Portkey,
LiteLLM, Lakera, and Protecto.

IMPORTANT -- READ BEFORE CITING ANY NUMBER FROM THIS FILE'S OUTPUT:
These are NOT measurements of the real Portkey/LiteLLM/Lakera/Protecto
products. This environment has no API keys, network access, or license
for any of them. Each "Mock*Runner" below is a small, independently
written stand-in reflecting only that product's PUBLIC POSITIONING:
  - Portkey/LiteLLM are LLM gateways/routers (observability, caching,
    fallback routing), not PII/content-safety products -- their mocks
    intentionally do NO content scanning at all.
  - Lakera Guard's public positioning centers on prompt-injection/
    jailbreak/content-moderation detection -- its mock runs only a
    naive, independent keyword heuristic (deliberately simpler than
    MonoAI's own G4 cascade), no PII detection.
  - Protecto's public positioning centers on PII tokenization/masking
    -- its mock runs a narrow, independent 3-pattern regex set
    (email/phone/credit-card only), no injection detection.
Latency numbers ARE real: every runner's own code is actually executed
and timed. What's illustrative is each mock's detection LOGIC, not the
timing measurement -- treat every number under "portkey_mock" /
"litellm_mock" / "lakera_mock" / "protecto_mock" as "what a simplistic
baseline of this shape scores on this synthetic set," never as a
competitive claim about the named product's real, undisclosed
detection quality.

Synthetic payload set: bench/corpora/en_pii.jsonl (PII ground truth) +
bench/corpora/injection.jsonl (injection/benign ground truth) --
already-existing, programmatically-generated starter corpora (see
DECISIONS.md re: corpus size/curation caveats), combined here into one
unified payload list so every runner sees the exact same inputs.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from contracts.policy import Action
from contracts.spans import TextUnit, TextUnitLocator
from detect.pipeline import DetectionPipeline
from detect.stages.injection_stage import InjectionDetector
from policy.engine import evaluate
from policy.store import PolicyStore

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO_ROOT / "bench" / "results"


@dataclass
class Payload:
    payload_id: str
    text: str
    expected_labels: set[str]
    is_injection: bool


@dataclass
class RunnerOutcome:
    detected_labels: set[str]
    blocked: bool  # overall accept/reject decision -- may be PII- or injection-triggered
    injection_flagged: bool  # specifically: did this runner's injection-detection component fire


class BaselineRunner(Protocol):
    name: str

    def process(self, text: str) -> RunnerOutcome: ...


def _load_payloads() -> list[Payload]:
    payloads: list[Payload] = []

    pii_path = REPO_ROOT / "bench" / "corpora" / "en_pii.jsonl"
    with open(pii_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            row = json.loads(line)
            payloads.append(Payload(
                payload_id=f"pii-{i}", text=row["text"],
                expected_labels=set(row["expected_labels"]), is_injection=False,
            ))

    injection_path = REPO_ROOT / "bench" / "corpora" / "injection.jsonl"
    with open(injection_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            row = json.loads(line)
            payloads.append(Payload(
                payload_id=f"inj-{i}", text=row["text"],
                expected_labels=set(), is_injection=(row["label"] == "attack"),
            ))

    return payloads


class MonoAIRunner:
    """The real thing: core/detect + core/policy composed the same way
    gateway/pii.py does, using policies/default.yaml with G4 injection
    detection turned on."""

    name = "monoai"

    def __init__(self) -> None:
        self._pipeline = DetectionPipeline(use_onnx_ner=False)
        store = PolicyStore()
        store.load_dir(str(REPO_ROOT / "policies"))
        base_policy = store.get("default")
        self._policy = base_policy.model_copy(update={
            "injection": base_policy.injection.model_copy(update={"enabled": True, "action": "BLOCK"}),
        })
        self._injection_detector = InjectionDetector.load()

    def process(self, text: str) -> RunnerOutcome:
        unit = TextUnit(
            unit_id="u", role="user", text=text,
            locator=TextUnitLocator(surface="chat_message", path="x"),
            turn_index=0, direction="input",
        )
        spans = self._pipeline.run([unit], policy_ctx=self._policy)
        decisions = evaluate(spans, self._policy)
        detected = {d.span.label.value for d in decisions if d.action != Action.PRESERVE}
        pii_blocked = any(d.action == Action.BLOCK for d in decisions)

        injection_result = self._injection_detector.detect(text, threshold=self._policy.injection.threshold)
        injection_flagged = injection_result.is_injection

        return RunnerOutcome(
            detected_labels=detected, blocked=pii_blocked or injection_flagged, injection_flagged=injection_flagged,
        )


# --- Mock baseline runners -- see module docstring; NOT the real products ---

class MockPortkeyRunner:
    """Portkey is an LLM gateway (routing/caching/observability), not a
    PII/content-safety product -- mock intentionally does no content
    scanning at all, matching that public positioning."""

    name = "portkey_mock"

    def process(self, text: str) -> RunnerOutcome:
        _ = len(text)  # trivial pass-through cost, still genuinely executed/timed
        return RunnerOutcome(detected_labels=set(), blocked=False, injection_flagged=False)


class MockLiteLLMRunner:
    """LiteLLM is a unified LLM API proxy/router, not a PII/content-safety
    product -- same no-content-scanning positioning as the Portkey mock."""

    name = "litellm_mock"

    def process(self, text: str) -> RunnerOutcome:
        _ = len(text)
        return RunnerOutcome(detected_labels=set(), blocked=False, injection_flagged=False)


_LAKERA_MOCK_KEYWORDS = re.compile(
    r"\b(ignore|disregard|forget)\b.{0,20}\b(instructions?|rules?)\b"
    r"|\b(jailbreak|unrestricted|no rules|roleplay as)\b",
    re.IGNORECASE,
)


class MockLakeraRunner:
    """Lakera Guard's public positioning centers on prompt-injection/
    jailbreak/content-moderation detection, not general PII redaction --
    mock runs ONLY a naive, independent keyword heuristic (deliberately
    simpler than MonoAI's own G4 cascade), no PII detection at all."""

    name = "lakera_mock"

    def process(self, text: str) -> RunnerOutcome:
        is_attack = bool(_LAKERA_MOCK_KEYWORDS.search(text))
        return RunnerOutcome(detected_labels=set(), blocked=is_attack, injection_flagged=is_attack)


_PROTECTO_MOCK_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PROTECTO_MOCK_PHONE_RE = re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")
_PROTECTO_MOCK_CC_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")


class MockProtectoRunner:
    """Protecto's public positioning centers on PII tokenization/masking
    -- mock runs a narrow, independent 3-pattern regex set (email/phone/
    credit-card only; no NER, no government-ID formats, no injection
    detection), deliberately narrower than MonoAI's full cascade."""

    name = "protecto_mock"

    def process(self, text: str) -> RunnerOutcome:
        detected = set()
        if _PROTECTO_MOCK_EMAIL_RE.search(text):
            detected.add("EMAIL")
        if _PROTECTO_MOCK_PHONE_RE.search(text):
            detected.add("PHONE")
        if _PROTECTO_MOCK_CC_RE.search(text):
            detected.add("CREDIT_CARD")
        return RunnerOutcome(detected_labels=detected, blocked=False, injection_flagged=False)


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = min(len(values) - 1, int(len(values) * p))
    return values[idx]


def _evaluate_runner(runner: BaselineRunner, payloads: list[Payload]) -> dict:
    latencies_ms: list[float] = []
    tp: dict[str, int] = {}
    fp: dict[str, int] = {}
    fn: dict[str, int] = {}
    injection_tp = injection_fp = injection_fn = injection_tn = 0

    t_start = time.perf_counter()
    for payload in payloads:
        t0 = time.perf_counter()
        outcome = runner.process(payload.text)
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)

        for label in outcome.detected_labels | payload.expected_labels:
            if label in outcome.detected_labels and label in payload.expected_labels:
                tp[label] = tp.get(label, 0) + 1
            elif label in outcome.detected_labels:
                fp[label] = fp.get(label, 0) + 1
            else:
                fn[label] = fn.get(label, 0) + 1

        if payload.is_injection and outcome.injection_flagged:
            injection_tp += 1
        elif payload.is_injection and not outcome.injection_flagged:
            injection_fn += 1
        elif not payload.is_injection and outcome.injection_flagged:
            injection_fp += 1
        else:
            injection_tn += 1
    wall_s = time.perf_counter() - t_start

    total_tp = sum(tp.values())
    total_fn = sum(fn.values())
    pii_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0.0

    return {
        "runner": runner.name,
        "n_payloads": len(payloads),
        "latency_ms": {
            "p50": round(_percentile(latencies_ms, 0.50), 4),
            "p99": round(_percentile(latencies_ms, 0.99), 4),
        },
        "throughput_rps": round(len(payloads) / wall_s, 2) if wall_s > 0 else None,
        "pii_recall": round(pii_recall, 4),
        "false_positive_splits": dict(sorted(fp.items())),
        "injection": {
            "tp": injection_tp, "fp": injection_fp, "fn": injection_fn, "tn": injection_tn,
            "recall": round(injection_tp / (injection_tp + injection_fn), 4) if (injection_tp + injection_fn) else 0.0,
        },
    }


_CAVEAT = (
    "portkey_mock/litellm_mock/lakera_mock/protecto_mock are NOT the real vendor "
    "products -- no API access/keys/license for any of them exists in this "
    "environment. Each is a small, independently-written stand-in reflecting only "
    "that product's public positioning (see bench/harness.py's module docstring "
    "and DECISIONS.md). Latency numbers are real measured execution time of each "
    "mock's own code; the mock's detection LOGIC is illustrative, not a "
    "competitive benchmark of the named product."
)


def run() -> dict:
    payloads = _load_payloads()
    runners: list[BaselineRunner] = [
        MonoAIRunner(), MockPortkeyRunner(), MockLiteLLMRunner(), MockLakeraRunner(), MockProtectoRunner(),
    ]
    results = [_evaluate_runner(r, payloads) for r in runners]
    return {
        "generated_at": time.time(),
        "n_payloads": len(payloads),
        "caveat": _CAVEAT,
        "results": results,
    }


def render_markdown(data: dict) -> str:
    lines = [
        "### Cross-runner synthetic benchmark (bench/harness.py)",
        "",
        f"> {data['caveat']}",
        "",
        "| Runner | p50 ms | p99 ms | throughput req/s | PII recall | injection recall | FP labels |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in data["results"]:
        fp_str = ", ".join(f"{k}:{v}" for k, v in r["false_positive_splits"].items()) or "none"
        lines.append(
            f"| {r['runner']} | {r['latency_ms']['p50']:.3f} | {r['latency_ms']['p99']:.3f} | "
            f"{r['throughput_rps']} | {r['pii_recall']:.2f} | {r['injection']['recall']:.2f} | {fp_str} |"
        )
    return "\n".join(lines)


def main() -> None:
    data = run()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results_path = RESULTS_DIR / "latest.json"
    results_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(render_markdown(data))
    print(f"\nwrote {results_path}")


if __name__ == "__main__":
    main()
