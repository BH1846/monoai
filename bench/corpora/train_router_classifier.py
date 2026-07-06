#!/usr/bin/env python3
"""Trains the TF-IDF + logistic regression router difficulty classifier
on bench/corpora/routing_labeled.jsonl, saves to
core/detect/packs/base_en/models/router_classifier.pkl.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

CORPUS_PATH = Path(__file__).parent / "routing_labeled.jsonl"
MODEL_PATH = (
    Path(__file__).parents[2] / "core" / "detect" / "packs" / "base_en" / "models" / "router_classifier.pkl"
)


def load_corpus(path: Path) -> tuple[list[str], list[str]]:
    texts, labels = [], []
    with open(path) as f:
        for line in f:
            row = json.loads(line)
            texts.append(row["text"])
            labels.append(row["difficulty"])
    return texts, labels


def main() -> None:
    texts, labels = load_corpus(CORPUS_PATH)

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1)),
        ("clf", LogisticRegression(max_iter=1000)),
    ])
    pipeline.fit(texts, labels)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(pipeline, f)
    print(f"trained on {len(texts)} examples, saved to {MODEL_PATH}")


if __name__ == "__main__":
    main()
