#!/usr/bin/env python3
"""P/R/F1 per label on bench/corpora/en_pii.jsonl. No Presidio comparison
in this pass (would add a new heavy dependency/setup step -- see
DECISIONS.md); the table has a placeholder column noting this.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from contracts.spans import TextUnit, TextUnitLocator
from detect.pipeline import DetectionPipeline

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = REPO_ROOT / "bench" / "corpora" / "en_pii.jsonl"


def run() -> dict:
    pipeline = DetectionPipeline(use_onnx_ner=False)
    tp: dict[str, int] = defaultdict(int)
    fp: dict[str, int] = defaultdict(int)
    fn: dict[str, int] = defaultdict(int)

    with open(CORPUS_PATH) as f:
        for line in f:
            row = json.loads(line)
            text, expected = row["text"], set(row["expected_labels"])

            unit = TextUnit(
                unit_id="u1", role="user", text=text,
                locator=TextUnitLocator(surface="chat_message", path="x"),
                turn_index=0, direction="input",
            )
            found = {s.label.value for s in pipeline.run([unit])}

            for label in found | expected:
                if label in found and label in expected:
                    tp[label] += 1
                elif label in found:
                    fp[label] += 1
                else:
                    fn[label] += 1

    results = {}
    for label in sorted(set(tp) | set(fp) | set(fn)):
        precision = tp[label] / (tp[label] + fp[label]) if (tp[label] + fp[label]) else 0.0
        recall = tp[label] / (tp[label] + fn[label]) if (tp[label] + fn[label]) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        results[label] = {"precision": precision, "recall": recall, "f1": f1}
    return results


def render_markdown(results: dict) -> str:
    lines = [
        "### PII detection (EN, bench/corpora/en_pii.jsonl -- see DECISIONS.md for corpus size caveat)",
        "",
        "| Label | Precision | Recall | F1 | vs. Presidio |",
        "|---|---|---|---|---|",
    ]
    for label, m in results.items():
        lines.append(f"| {label} | {m['precision']:.2f} | {m['recall']:.2f} | {m['f1']:.2f} | not run |")
    return "\n".join(lines)


if __name__ == "__main__":
    print(render_markdown(run()))
