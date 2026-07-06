"""Stage 2 of the router cascade (G7): a lightweight classifier trained
on bench/corpora/routing_labeled.jsonl via
bench/corpora/train_router_classifier.py.

NOT real MiniLM embeddings + a sidecar (per the master plan's
ner-sidecar design) -- see DECISIONS.md. TF-IDF + logistic regression
substitutes for "an embedding classifier" at "complete it fast" speed;
the cascade shape (heuristic first, this as a confirming/overriding
second opinion) is real and swappable later for a true embedding model
behind the same interface.
"""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import Optional

DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parents[2] / "core" / "detect" / "packs" / "base_en" / "models" / "router_classifier.pkl"
)


class EmbeddingRouterClassifier:
    def __init__(self, classifier: Optional[object] = None) -> None:
        self._classifier = classifier

    @classmethod
    def load(cls, model_path: Optional[Path] = None) -> "EmbeddingRouterClassifier":
        path = model_path or DEFAULT_MODEL_PATH
        if not path.is_file():
            return cls(classifier=None)
        with open(path, "rb") as f:
            classifier = pickle.load(f)  # noqa: S301 -- first-party artifact
        return cls(classifier=classifier)

    def classify(self, text: str) -> Optional[str]:
        if self._classifier is None:
            return None
        return str(self._classifier.predict([text])[0])


def classify_difficulty_cascade(
    text: str, heuristic_result: str, embedding_classifier: Optional[EmbeddingRouterClassifier]
) -> str:
    """Stage 1 (heuristic) already ran -- this stage confirms or
    overrides with the trained classifier when available, falling back
    to the heuristic result otherwise (fail-open on this optional
    upgrade, not a data-path invariant)."""
    if embedding_classifier is None:
        return heuristic_result
    embedding_result = embedding_classifier.classify(text)
    return embedding_result or heuristic_result
