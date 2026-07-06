"""G7 proof tests: embedding-style router cascade accuracy vs. heuristic
baseline, and per-stage latency budget."""
import json
import time
from pathlib import Path

from router.embedding_classifier import EmbeddingRouterClassifier, classify_difficulty_cascade
from router.heuristic import classify_difficulty

CORPUS_PATH = Path(__file__).resolve().parents[2] / "bench" / "corpora" / "routing_labeled.jsonl"


def _load_corpus() -> list[dict]:
    rows = []
    with open(CORPUS_PATH) as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def test_cascade_agrees_on_labeled_set_better_than_heuristic_alone():
    rows = _load_corpus()
    classifier = EmbeddingRouterClassifier.load()

    heuristic_correct = sum(1 for r in rows if classify_difficulty(r["text"]) == r["difficulty"])
    cascade_correct = 0
    for r in rows:
        heuristic_result = classify_difficulty(r["text"])
        cascade_result = classify_difficulty_cascade(r["text"], heuristic_result, classifier)
        cascade_correct += cascade_result == r["difficulty"]

    heuristic_acc = heuristic_correct / len(rows)
    cascade_acc = cascade_correct / len(rows)

    # Trained on this exact corpus (no held-out split, unlike test_injection.py)
    # -- this proves the cascade WIRING is correct and beats the heuristic
    # baseline, not held-out generalization (see DECISIONS.md).
    assert cascade_acc >= heuristic_acc


def test_embedding_stage_latency_budget():
    classifier = EmbeddingRouterClassifier.load()
    text = "Write a Python function to reverse a linked list."

    t0 = time.perf_counter()
    for _ in range(20):
        classifier.classify(text)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0 / 20

    assert elapsed_ms < 25.0, f"embedding stage p-ish latency {elapsed_ms}ms exceeds 25ms budget"


def test_cascade_falls_back_to_heuristic_when_no_model():
    result = classify_difficulty_cascade("hi there", "simple", embedding_classifier=None)
    assert result == "simple"
