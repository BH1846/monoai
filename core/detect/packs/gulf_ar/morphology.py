"""Arabic morphology: strip commonly fused prefixes/suffixes before
token/gazetteer matching (Phase 4, gulf_ar pack).

Arabic attaches conjunctions/prepositions/the definite article directly
onto the following word with no whitespace (و + الاسم = "and the name"
becomes والاسم), and attaches possessive/plural suffixes directly onto
the end (اسمها = "her name"). A cue-word or gazetteer lookup that only
knows the bare form ("اسم") would silently miss most real-world
occurrences without stripping these first.

This is a standard "light stemmer" approach (c.f. Larkey et al.'s
Light10 Arabic stemmer) -- good enough to normalize a token before an
exact-match cue-word lookup, not a full morphological analyzer.
"""
from __future__ import annotations

import re

# Longest-first so a multi-letter fused prefix (e.g. "بال" = by+the) is
# stripped as one unit rather than leaving a dangling "ال" a second,
# shorter-prefix pass would also match.
_PREFIXES = ("بال", "كال", "وال", "فال", "لل", "ال", "و", "ف", "ب", "ل", "ك")

# Longest-first for the same reason, applied after prefix stripping.
_SUFFIXES = ("هما", "كما", "تان", "تين", "ون", "ين", "ات", "ها", "هم", "هن", "نا", "كم", "كن", "ية", "ه", "ي", "ا")

_ARABIC_WORD_RE = re.compile(r"[ء-ي]+")


def strip_prefixes(token: str) -> str:
    for prefix in _PREFIXES:
        # +1: never strip a prefix down to nothing or a single leftover
        # letter -- that's almost certainly the whole word, not a
        # prefix+stem split (e.g. don't reduce "لا" to "ا").
        if token.startswith(prefix) and len(token) > len(prefix) + 1:
            return token[len(prefix):]
    return token


def strip_suffixes(token: str) -> str:
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) > len(suffix) + 1:
            return token[: -len(suffix)]
    return token


def normalize_token(token: str) -> str:
    """Strip prefix first, then suffix -- a single token can carry both
    (e.g. والدتها = وَ + والدة + ها, "and his mother")."""
    return strip_suffixes(strip_prefixes(token))


def tokenize_arabic(text: str) -> list[str]:
    return _ARABIC_WORD_RE.findall(text)


# Deliberately narrow cue-word list for Gulf ID context boosting (see
# ids.py's has_id_cue_nearby) -- not a general Arabic NLP vocabulary.
ID_CUE_WORDS = {
    "هوية",   # identity
    "بطاقة",  # card
    "اقامة",  # residence / iqama
    "رقم",    # number
    "جنسية",  # nationality
    "مدني",   # civil (as in "civil ID/number")
    "سجل",    # record / register
}


def has_id_cue_nearby(text: str, start: int, end: int, window: int = 40) -> bool:
    """Looks for an ID-related Arabic cue word in the text immediately
    surrounding a candidate digit span, after morphological stripping
    (so "بالهوية" or "للاقامة" still match "هوية"/"اقامة"). Used to
    boost confidence for ID formats with no publicly documented
    checksum (Qatar QID, Bahrain CPR, Oman civil number), where
    structural pattern matching alone is otherwise the only signal."""
    window_start = max(0, start - window)
    window_end = min(len(text), end + window)
    nearby = text[window_start:window_end]
    return any(normalize_token(tok) in ID_CUE_WORDS for tok in tokenize_arabic(nearby))
