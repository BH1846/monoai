"""Stage 1: sentence_split — English-only, no language routing.

Ported near-verbatim from SENTINEL-2.0/pii_pipeline/sentence_split.py.
Gives locked_span_stage smaller, locally-coherent windows so negation
scoping doesn't bleed across sentences.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "e.g",
    "i.e", "inc", "ltd", "co", "corp", "no", "approx", "fig", "u.s", "u.k",
}

_SENTENCE_END_RE = re.compile(r"[.!?]+[\"')\]]*(\s+|$)")
_LAST_WORD_RE = re.compile(r"(\w[\w.]*)$")


@dataclass
class Sentence:
    text: str
    start: int
    end: int


def split_sentences(text: str) -> list[Sentence]:
    """Split text into sentences, returning original character offsets.

    O(n) in len(text): one forward scan using finditer, no backtracking
    beyond the fixed-size abbreviation lookback.
    """
    if not text:
        return []

    sentences: list[Sentence] = []
    start = 0
    for match in _SENTENCE_END_RE.finditer(text):
        boundary = match.end()
        candidate = text[start:match.start()]

        last_word_match = _LAST_WORD_RE.search(candidate)
        last_word = last_word_match.group(1).lower() if last_word_match else ""
        if last_word in _ABBREVIATIONS:
            continue  # not a real sentence boundary, keep accumulating

        sentence_text = text[start:boundary]
        if sentence_text.strip():
            sentences.append(Sentence(text=sentence_text, start=start, end=boundary))
        start = boundary

    if start < len(text) and text[start:].strip():
        sentences.append(Sentence(text=text[start:], start=start, end=len(text)))

    return sentences
