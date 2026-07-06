#!/usr/bin/env python3
"""Router accuracy on bench/corpora/routing_labeled.jsonl: heuristic
baseline vs. the G7 cascade (heuristic + lightweight classifier).
`--train` retrains the classifier first (calls train_router_classifier.py).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from router.embedding_classifier import EmbeddingRouterClassifier, classify_difficulty_cascade
from router.heuristic import classify_difficulty

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = REPO_ROOT / "bench" / "corpora" / "routing_labeled.jsonl"


def run() -> dict:
    rows = []
    with open(CORPUS_PATH) as f:
        for line in f:
            rows.append(json.loads(line))

    classifier = EmbeddingRouterClassifier.load()

    heuristic_correct = 0
    cascade_correct = 0
    latencies_ms = []

    for row in rows:
        text, expected = row["text"], row["difficulty"]
        heuristic_result = classify_difficulty(text)
        heuristic_correct += heuristic_result == expected

        t0 = time.perf_counter()
        cascade_result = classify_difficulty_cascade(text, heuristic_result, classifier)
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        cascade_correct += cascade_result == expected

    latencies_ms.sort()
    p95 = latencies_ms[int(len(latencies_ms) * 0.95) - 1] if latencies_ms else 0.0

    return {
        "n": len(rows),
        "heuristic_accuracy": heuristic_correct / len(rows),
        "cascade_accuracy": cascade_correct / len(rows),
        "cascade_p95_ms": p95,
    }


def render_markdown(results: dict) -> str:
    return (
        "### Router accuracy (bench/corpora/routing_labeled.jsonl, "
        f"n={results['n']} -- see DECISIONS.md for corpus size caveat)\n\n"
        "| Stage | Accuracy | p95 latency |\n"
        "|---|---|---|\n"
        f"| Heuristic only | {results['heuristic_accuracy']:.2f} | n/a |\n"
        f"| Cascade (+ classifier) | {results['cascade_accuracy']:.2f} | {results['cascade_p95_ms']:.2f}ms |\n"
    )


if __name__ == "__main__":
    if "--train" in sys.argv:
        import subprocess

        subprocess.run([sys.executable, str(REPO_ROOT / "bench" / "corpora" / "train_router_classifier.py")], check=True)
    print(render_markdown(run()))
