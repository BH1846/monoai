"""Stage 1 of the router cascade: heuristic difficulty classifier. Ported
verbatim from Lite_Multimodel_switching/monoai_router/lite/classifier.py.
Stage 2 (embedding classifier via ner-sidecar) is Phase 2.
"""
from __future__ import annotations

import re

_HARD_SIGNALS = re.compile(
    r"\b(prove|derive|optimi[sz]e|theorem|multi[\s-]?step|step[\s-]by[\s-]step|"
    r"design\s+a\s+system|system\s+design|architecture|distributed)\b",
    re.IGNORECASE,
)
_MODERATE_SIGNALS = re.compile(
    r"\b(def|class|function|write\s+(a|an)?\s*(code|program|script|function)|"
    r"solve|calculate|compute|equation|design|implement|build|refactor|"
    r"thread[\s-]?safe|async|concurren\w*|cache|algorithm|data\s?structure|"
    r"unit\s+test|error\s+handling)\b",
    re.IGNORECASE,
)

_CONCURRENCY_SIGNAL = re.compile(r"\b(thread-safe|concurrent\w*|async)\b", re.IGNORECASE)
_ROBUSTNESS_SIGNAL = re.compile(r"\b(unit\s+tests?|error\s+handling)\b", re.IGNORECASE)
_LEADING_VERB_SIGNAL = re.compile(r"^\s*(design|implement)\b", re.IGNORECASE)
_CONJUNCTION = re.compile(r"\band\b", re.IGNORECASE)

_MULTIPLE_CHOICE_SIGNAL = re.compile(
    r"\bA\)\s*\S.*\bB\)\s*\S.*\bC\)\s*\S", re.DOTALL
)

_MATH_NOTATION_SIGNAL = re.compile(
    r"\\(frac|sqrt|sum|prod|int|lim|binom|boxed|overline|angle|triangle|cdot)\b"
    r"|[∑∫∏√∞≤≥≠≈±×÷]"
)

_NUMBER_SIGNAL = re.compile(r"\d+")


def _complexity_score(text: str, token_count: int) -> int:
    score = 0
    if _CONCURRENCY_SIGNAL.search(text):
        score += 1
    if _ROBUSTNESS_SIGNAL.search(text):
        score += 1
    if _LEADING_VERB_SIGNAL.match(text):
        score += 1
    if token_count > 30:
        score += 1
    if len(_CONJUNCTION.findall(text)) > 3:
        score += 1
    return score


def _is_math_heavy(text: str) -> bool:
    return bool(_MATH_NOTATION_SIGNAL.search(text)) or text.count("$") >= 4


def _is_math_word_problem(text: str, token_count: int) -> bool:
    return token_count <= 50 and len(_NUMBER_SIGNAL.findall(text)) >= 3


def classify_difficulty(text: str) -> str:
    """Return 'simple', 'moderate', or 'complex' for the given prompt text."""
    token_count = len(text.split())

    if (
        token_count > 150
        or _HARD_SIGNALS.search(text)
        or _is_math_heavy(text)
        or _complexity_score(text, token_count) >= 2
    ):
        return "complex"
    if (
        token_count > 50
        or _MODERATE_SIGNALS.search(text)
        or _MULTIPLE_CHOICE_SIGNAL.search(text)
        or _is_math_word_problem(text, token_count)
    ):
        return "moderate"
    return "simple"
