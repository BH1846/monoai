"""G7: embedding-based routing cascade, tier selected by labeled corpus
size N (bench/corpora/routing_labeled.jsonl):

    N < 50        -> anchor-based semantic similarity heuristic
    50 <= N < 300 -> SetFit-style few-shot classifier
    N >= 300      -> fine-tuned ONNX DistilBERT classifier

SUBSTITUTION (see DECISIONS.md): the 50<=N<300 and N>=300 tiers are NOT
real SetFit/sentence-transformers or a fine-tuned ONNX DistilBERT model
-- both require torch/sentence-transformers (multi-GB) plus either a
HuggingFace Hub download or an actual fine-tuning job, neither
available nor a good trade for this phase (user confirmed: lightweight
substitute, same cascade). Both tiers are real, trained-at-construction
TF-IDF + scikit-learn models behind the exact same `.classify(text) ->
RouterDecision` interface as a real SetFit/ONNX model would expose, so
swapping the real libraries in later only touches this file:
  - "setfit" tier: word 1-2gram TF-IDF + calibrated logistic regression
    (approximates SetFit's few-shot classification head).
  - "onnx_distilbert" tier: char 3-5gram TF-IDF + logistic regression
    (approximates a subword-tokenizer model's finer-grained signal).

This is a distinct, more principled successor to
gateway/router/embedding_classifier.py's ad hoc single TF-IDF stage
(kept in place, untouched, for its own tests) -- this module is the
real "route by how much labeled data you actually have" governance
layer G7 asks for, including per-decision confidence + rationale for
audit/observability.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity

DEFAULT_CORPUS_PATH = (
    Path(__file__).resolve().parents[2] / "bench" / "corpora" / "routing_labeled.jsonl"
)

SETFIT_TIER_MIN = 50
ONNX_TIER_MIN = 300

# Hardcoded per-class anchors for the N<50 tier -- no training data
# required at all; this is what lets the router degrade gracefully to
# "closest known example" instead of refusing to route when a fresh
# deployment hasn't labeled anything yet.
_ANCHOR_EXAMPLES: dict[str, list[str]] = {
    "simple": [
        "Hi, how are you?",
        "What is 2 plus 2?",
        "Say hello to my friend.",
        "Thanks so much!",
        "What's the capital of France?",
        "Good morning!",
    ],
    "moderate": [
        "Summarize this paragraph in three sentences.",
        "Explain how photosynthesis works.",
        "Write a short product description for a running shoe.",
        "Compare Python and JavaScript for web development.",
        "Draft a polite email declining a meeting invite.",
    ],
    "complex": [
        "Design a distributed rate limiter that handles clock skew across regions.",
        "Prove that the halting problem is undecidable.",
        "Write a multi-step migration plan from a monolith to microservices with a rollback strategy.",
        "Derive the gradient of a transformer's attention mechanism with respect to its query weights.",
        "Design a sovereignty-grade PII vault schema with TTL and right-to-erasure.",
    ],
}


@dataclass
class RouterDecision:
    """G7 output: per-message decision + confidence + rationale, meant
    to be attached to request-level audit meta -- never applied by a
    caller without also recording how the decision was reached."""

    difficulty: str
    confidence: float
    tier: str  # "anchor_similarity" | "setfit" | "onnx_distilbert"
    rationale: str
    corpus_size: int = 0


def _load_corpus(path: Path) -> list[tuple[str, str]]:
    if not path.is_file():
        return []
    examples: list[tuple[str, str]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            examples.append((row["text"], row["difficulty"]))
    return examples


class _AnchorSimilarityRouter:
    """N<50 tier."""

    def __init__(self, anchors: dict[str, list[str]] = _ANCHOR_EXAMPLES) -> None:
        labels: list[str] = []
        docs: list[str] = []
        for label, examples in anchors.items():
            for ex in examples:
                labels.append(label)
                docs.append(ex)
        self._labels = labels
        self._vectorizer = TfidfVectorizer()
        self._matrix = self._vectorizer.fit_transform(docs)

    def classify(self, text: str) -> RouterDecision:
        vec = self._vectorizer.transform([text])
        sims = cosine_similarity(vec, self._matrix)[0]
        best_idx = int(sims.argmax())
        best_label = self._labels[best_idx]
        confidence = float(sims[best_idx])
        return RouterDecision(
            difficulty=best_label,
            confidence=round(confidence, 4),
            tier="anchor_similarity",
            rationale=(
                f"N<{SETFIT_TIER_MIN}: closest anchor example matched "
                f"{best_label!r} (cosine similarity={confidence:.3f})"
            ),
        )


class _TrainedTfidfRouter:
    """Shared shape for the setfit-style and onnx_distilbert-style
    tiers -- both fit a TF-IDF + logistic regression model over the
    labeled corpus at construction time, differing only in vectorizer
    settings (see module docstring re: substitution)."""

    def __init__(self, corpus: list[tuple[str, str]], vectorizer: TfidfVectorizer, tier: str) -> None:
        texts = [t for t, _ in corpus]
        labels = [d for _, d in corpus]
        self._tier = tier
        self._vectorizer = vectorizer
        x = self._vectorizer.fit_transform(texts)
        self._model = LogisticRegression(max_iter=1000, class_weight="balanced")
        self._model.fit(x, labels)

    def classify(self, text: str) -> RouterDecision:
        vec = self._vectorizer.transform([text])
        proba = self._model.predict_proba(vec)[0]
        classes = [str(c) for c in self._model.classes_]  # sklearn stores these as numpy.str_
        best_idx = int(proba.argmax())
        best_label = classes[best_idx]
        confidence = float(proba[best_idx])
        return RouterDecision(
            difficulty=best_label,
            confidence=round(confidence, 4),
            tier=self._tier,
            rationale=(
                f"{self._tier} classifier: P({best_label!r})={confidence:.3f} "
                f"over {len(classes)} classes, trained on corpus"
            ),
        )


def _setfit_style_router(corpus: list[tuple[str, str]]) -> _TrainedTfidfRouter:
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)
    return _TrainedTfidfRouter(corpus, vectorizer, tier="setfit")


def _onnx_distilbert_style_router(corpus: list[tuple[str, str]]) -> _TrainedTfidfRouter:
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1)
    return _TrainedTfidfRouter(corpus, vectorizer, tier="onnx_distilbert")


class EmbeddingRouter:
    """G7 entrypoint. Picks a tier at construction time based on how
    many labeled examples are available, and exposes `.classify(text)
    -> RouterDecision` uniformly regardless of tier."""

    def __init__(self, corpus_path: Optional[Path] = None) -> None:
        path = corpus_path or DEFAULT_CORPUS_PATH
        corpus = _load_corpus(path)
        self._n = len(corpus)
        distinct_labels = {d for _, d in corpus}

        if self._n < SETFIT_TIER_MIN or len(distinct_labels) < 2:
            self._impl: object = _AnchorSimilarityRouter()
            self._tier = "anchor_similarity"
        elif self._n < ONNX_TIER_MIN:
            self._impl = _setfit_style_router(corpus)
            self._tier = "setfit"
        else:
            self._impl = _onnx_distilbert_style_router(corpus)
            self._tier = "onnx_distilbert"

    @classmethod
    def load(cls, corpus_path: Optional[Path] = None) -> "EmbeddingRouter":
        return cls(corpus_path)

    @property
    def corpus_size(self) -> int:
        return self._n

    @property
    def tier(self) -> str:
        return self._tier

    def classify(self, text: str) -> RouterDecision:
        decision = self._impl.classify(text)  # type: ignore[attr-defined]
        decision.corpus_size = self._n
        return decision
