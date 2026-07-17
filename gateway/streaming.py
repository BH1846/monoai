"""SSE relay + sliding-window rehydrator (G1).

session_tokens.py's placeholders are now type-labeled
(`<{LABEL}_PII_xxxxxxxxxx>`), so a token's width varies BY TYPE but is
bounded: the longest possible token across all SpanLabels is
`MAX_TOKEN_LEN` characters (e.g. `<CREDIT_CARD_PII_xxxxxxxxxx>`). An
incomplete prefix of ANY type is therefore at most `MAX_TOKEN_LEN - 1`
characters (one more char and the longest token would be complete), so a
single closed-form holdback of that size still bounds everything "in
flight" -- no per-type state machine needed, just a holdback sized to the
longest token instead of a single fixed width.

A first version of this module held back a flat HOLDBACK characters on
every flush and released everything else unconditionally. That's enough to
keep an *incomplete* prefix out of the flush region, but two real bugs
surfaced during manual end-to-end testing:

1. Off-by-one: the instant a token becomes fully complete (all its chars
   present, nothing more), a flat HOLDBACK leaves its leading `<` one
   character short of the tail window, splitting it off a chunk early (the
   opening `<` flushed alone, the rest stranded next with no bracket to
   pair with).
2. Fragmentation: flushing unconditionally in small increments (however
   much exceeds the holdback on each new chunk) can release a token's
   bytes across *several separate* `_process()` calls, each of which only
   ever sees a slice too small to regex-match a whole token, so it's
   never rehydrated at all even once every byte has technically arrived.

`_split` below fixes both: it finds the last `<` before the naive split
point and (a) pulls the split back before it if the token there is still
incomplete, or (b) pushes the split forward past it if the token is
complete but would otherwise straddle the boundary -- so a token is
always handed to `_process()` as one whole, contiguous string exactly
once, never fragmented.

Order per flush region matters: output-scan (G5) runs FIRST on the raw
(not-yet-rehydrated) text -- existing `<..._PII_...>` placeholders are
protected from re-detection (see PiiEngine.scan_output) -- THEN
rehydrate resolves the original input-side placeholders.
"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator

from obs.tracing import stage_span
from pii import PiiEngine
from policy.schema import Policy
from vault.session_tokens import MAX_TOKEN_LEN, TOKEN_RE

# Holdback is sized to the LONGEST possible token across all types, so an
# incomplete token of any type is always kept out of the flush region.
TOKEN_LEN = MAX_TOKEN_LEN  # 28: <CREDIT_CARD_PII_xxxxxxxxxx> / <DEMOGRAPHIC_PII_xxxxxxxxxx>
HOLDBACK = TOKEN_LEN - 1
FIRST_FLUSH_DEADLINE_MS = 40.0

# Shared with gateway/pii.py -- single source of truth for the wire format.
_TOKEN_RE = TOKEN_RE


class StreamRehydrator:
    """One instance per streaming request. After `run()` is exhausted,
    `unresolved`/`review_required`/`raw_output`/`ttfb_ms` are populated for
    the caller to build the audit record from."""

    def __init__(self, session_id: str, pii: PiiEngine, policy: Policy, input_token_ids: set[str]) -> None:
        self._session_id = session_id
        self._pii = pii
        self._policy = policy
        self._input_token_ids = input_token_ids
        self._output_token_ids: set[str] = set()
        self.unresolved: list[str] = []
        self.review_required = False
        self.raw_output = ""
        self.ttfb_ms: float | None = None

    async def run(self, upstream: AsyncIterator[str]) -> AsyncIterator[str]:
        buffer = ""
        t_start = time.monotonic()
        flushed_once = False

        async for chunk in upstream:
            self.raw_output += chunk
            buffer += chunk

            past_deadline = (time.monotonic() - t_start) * 1000.0 > FIRST_FLUSH_DEADLINE_MS
            if len(buffer) > HOLDBACK or (not flushed_once and past_deadline):
                flush_region, buffer = self._split(buffer)
                if flush_region:
                    processed = self._process(flush_region)
                    # Compute ttfb BEFORE yielding: code after a `yield` in an
                    # async generator only runs once the consumer resumes it
                    # (calls __anext__ again) -- a consumer that stops after
                    # the first item (e.g. `break`) would otherwise leave
                    # ttfb_ms permanently None.
                    if not flushed_once:
                        flushed_once = True
                        self.ttfb_ms = (time.monotonic() - t_start) * 1000.0
                    yield processed

        if buffer:
            processed = self._process(buffer)
            if not flushed_once:
                self.ttfb_ms = (time.monotonic() - t_start) * 1000.0
            yield processed

    @staticmethod
    def _split(buffer: str) -> tuple[str, str]:
        if len(buffer) <= HOLDBACK:
            return "", buffer

        split_at = len(buffer) - HOLDBACK
        idx = buffer.rfind("<", 0, split_at)
        if idx != -1:
            m = _TOKEN_RE.match(buffer, idx)
            if m:
                # A complete token starts here and may extend past the
                # naive split point -- include it whole rather than
                # cutting through it.
                split_at = max(split_at, m.end())
            else:
                # Either an in-progress token or an unrelated literal
                # '<' -- don't flush past it either way; safe, just
                # possibly conservative for the unrelated-bracket case.
                split_at = idx

        return buffer[:split_at], buffer[split_at:]

    def _process(self, flush_region: str) -> str:
        # include_ner=False: a flush region is an arbitrary, often
        # mid-word/mid-sentence fragment -- see scan_output's docstring
        # for why NER is unreliable (and can corrupt legitimate output)
        # at this granularity. Regex/secrets detectors stay on.
        with stage_span("streaming_rehydrate", session_id=self._session_id, flush_region_len=len(flush_region)):
            if self._policy.output_scan.enabled:
                scanned, new_tokens = self._pii.scan_output(
                    flush_region, self._session_id, self._policy, include_ner=False
                )
                self._output_token_ids |= new_tokens
            else:
                # Output scanning disabled: pass the model's output through
                # untouched; only input-side tokens get rehydrated below.
                scanned = flush_region
            final_text, unresolved, review_required = self._pii.rehydrate(
                scanned, self._session_id, self._input_token_ids, self._output_token_ids
            )
        if unresolved:
            self.unresolved.extend(unresolved)
            self.review_required = True
        return final_text
