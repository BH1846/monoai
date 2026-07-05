"""normalize.py — offset-preserving text normalization that defeats common
detection-evasion tricks (zero-width characters, full-width unicode
lookalikes, single-character spacing like "j o h n @ mail . com") before
regex/NER matching runs, while letting every downstream stage keep
operating on ORIGINAL text offsets.

Ported near-verbatim from SENTINEL-2.0/pii_pipeline/normalize.py.

O(n) in text length: one linear character pass plus one bounded regex scan.
"""
from __future__ import annotations

import re
import unicodedata

_ZERO_WIDTH = {
    "​",  # zero-width space
    "‌",  # zero-width non-joiner
    "‍",  # zero-width joiner
    "⁠",  # word joiner
    "﻿",  # zero-width no-break space / BOM
}

# 4+ single-character tokens separated by lone spaces -- "j o h n" style
# de-obfuscation. See the lookaround note: guards stop the match from
# bleeding one character into an adjacent normal word on either side.
_SPACED_RUN_RE = re.compile(r"(?<!\w)(?:\S ){3,}\S(?!\w)")


def _fold_char(ch: str) -> str:
    """NFKC-fold a single character but only keep the fold when it stays
    1:1 -- some NFKC folds expand to multiple characters, and accepting
    those would desync the offset map."""
    folded = unicodedata.normalize("NFKC", ch)
    return folded if len(folded) == 1 else ch


def normalize_with_offsets(text: str) -> tuple[str, list[int]]:
    """Returns (normalized_text, offset_map) where offset_map[i] is the
    index into the ORIGINAL `text` that produced normalized_text[i]. Every
    retained character maps 1:1 back to exactly one original index;
    dropped characters (zero-width, de-obfuscated spaces) simply have no
    entry, so len(offset_map) == len(normalized_text) always.
    """
    if not text:
        return text, []

    chars: list[str] = []
    offsets: list[int] = []
    for i, ch in enumerate(text):
        if ch in _ZERO_WIDTH:
            continue
        chars.append(_fold_char(ch))
        offsets.append(i)

    folded = "".join(chars)

    drop = [False] * len(folded)
    for m in _SPACED_RUN_RE.finditer(folded):
        start, end = m.span()
        for j in range(start, end):
            if folded[j] == " " and (j - start) % 2 == 1:
                drop[j] = True

    out_chars = [c for j, c in enumerate(chars) if not drop[j]]
    out_offsets = [o for j, o in enumerate(offsets) if not drop[j]]
    return "".join(out_chars), out_offsets


def map_span(offset_map: list[int], orig_len: int, start: int, end: int) -> tuple[int, int]:
    """Map a half-open (start, end) span in normalized-text coordinates
    back to coordinates in the original text the offset_map was built
    from. `orig_len` is used for the degenerate empty-map case only."""
    if not offset_map:
        return 0, 0
    orig_start = offset_map[start] if start < len(offset_map) else orig_len
    orig_end = offset_map[end - 1] + 1 if end > 0 else orig_start
    return orig_start, orig_end
