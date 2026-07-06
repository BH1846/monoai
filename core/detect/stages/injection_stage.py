"""Prompt-injection / jailbreak detection stage (G4).

Two layers:
1. Heuristic pre-filter: known override/roleplay/exfiltration phrase
   patterns -- fast, deterministic, catches the obvious cases.
2. Lightweight classifier (TF-IDF + logistic regression, trained on
   bench/corpora/injection.jsonl via bench/corpora/train_injection_classifier.py)
   -- catches paraphrases the heuristic patterns miss.

NOT a downloaded transformer (e.g. Prompt-Guard-class model) as the
master plan's ner-sidecar envisions -- see DECISIONS.md. This is a
"complete it fast" Phase 2 substitution: real architecture (heuristic +
trainable classifier + policy-gated threshold), but trained on a small
~300-example generated corpus rather than a production-curated one.
"""
from __future__ import annotations

import pickle
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_OVERRIDE_RE = re.compile(
    r"\b(ignore|disregard|forget|override)\b.{0,25}\b(previous|prior|all|above|system|your)\b"
    r".{0,25}\b(instructions?|rules?|guidelines?|prompt)\b",
    re.IGNORECASE,
)
_ROLEPLAY_RE = re.compile(
    r"\b(you are now|act as if|pretend (you are|to be)|roleplay as|simulate being)\b.{0,40}"
    r"\b(no (restrictions|rules|filters|limits)|unrestricted|DAN|developer mode|no content policy)\b",
    re.IGNORECASE,
)
_EXFIL_RE = re.compile(
    r"\b(reveal|print|show|output|repeat)\b.{0,25}\b(your |the )?"
    r"(system prompt|instructions|configuration|hidden|everything above)\b",
    re.IGNORECASE,
)

_HEURISTIC_PATTERNS = {"override": _OVERRIDE_RE, "roleplay": _ROLEPLAY_RE, "exfiltration": _EXFIL_RE}

DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parents[1] / "packs" / "base_en" / "models" / "injection_classifier.pkl"
)


@dataclass
class InjectionResult:
    is_injection: bool
    score: float
    matched_heuristics: list[str] = field(default_factory=list)


def heuristic_matches(text: str) -> list[str]:
    return [name for name, pattern in _HEURISTIC_PATTERNS.items() if pattern.search(text)]


class InjectionDetector:
    """Works heuristic-only if no trained classifier is available/loaded
    -- still catches the known-pattern majority, just without paraphrase
    generalization."""

    def __init__(self, classifier: Optional[object] = None) -> None:
        self._classifier = classifier

    @classmethod
    def load(cls, model_path: Optional[Path] = None) -> "InjectionDetector":
        path = model_path or DEFAULT_MODEL_PATH
        if not path.is_file():
            return cls(classifier=None)
        with open(path, "rb") as f:
            classifier = pickle.load(f)  # noqa: S301 -- first-party artifact, not untrusted input
        return cls(classifier=classifier)

    def detect(self, text: str, threshold: float = 0.5) -> InjectionResult:
        matched = heuristic_matches(text)
        if matched:
            return InjectionResult(is_injection=True, score=1.0, matched_heuristics=matched)

        if self._classifier is None:
            return InjectionResult(is_injection=False, score=0.0, matched_heuristics=[])

        score = float(self._classifier.predict_proba([text])[0][1])
        return InjectionResult(is_injection=score >= threshold, score=score, matched_heuristics=[])
