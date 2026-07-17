"""Session-scoped, value-deterministic token IDs — closes G8.

The old SENTINEL-2.0 scheme (`sanitize.py`'s `build_sanitized_prompt`) used
a per-call counter (`PII_TOKEN_0001`, `0002`, ...): calling sanitize twice
in the same session restarts the counter, and since the vault key is
`(session_id, token_id)` with an upsert-on-conflict write, a second call
silently overwrites the first call's entries wherever the counter index
recurs. This module replaces that with a deterministic HMAC: the same
value always gets the same token within a session, and different sessions
never produce colliding tokens for the same value (session-scoped, not
globally deterministic — so tokens aren't a cross-session correlation
oracle).

## Surface format (type-labeled placeholders)

Placeholders are type-labeled — `<{LABEL}_PII_{token_id}>` — so the entity
type is visible in the token itself (e.g. `<EMAIL_PII_a1b2c3d4e5>`,
`<PHONE_PII_a1b2c3d4e5>`). The value's real structure is deliberately NOT
preserved: no real domains, no real digit groupings — just the type label
plus the opaque 10-hex id, uniformly across every type.

`make_token_id` (the deterministic HMAC) is unchanged; only the wrapping
format around the id varies. The 10-hex id is always embedded verbatim:
rehydration reverses a placeholder by extracting that id and doing
`vault.get(session_id, token_id)`.

Width now varies BY TYPE (`<ORG_PII_…>` is shorter than
`<CREDIT_CARD_PII_…>`) but is fixed WITHIN a type. `TOKEN_RE` and
`MAX_TOKEN_LEN` are the single source of truth for the wire format, imported
by both gateway/pii.py (detect/rehydrate) and gateway/streaming.py. Because
the max width across all types is bounded (`MAX_TOKEN_LEN`), streaming keeps
a simple closed-form holdback sized to the LONGEST possible token instead of
a per-type regex state machine (see streaming.py).
"""
from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata

from contracts.spans import SpanLabel

TOKEN_ID_LEN = 10


def derive_session_key(session_id: str, server_secret: str) -> bytes:
    """One per-deployment secret (SESSION_TOKEN_SECRET) + the session_id ->
    a session-scoped HMAC key. Cheap to recompute; never persisted."""
    return hashlib.sha256(f"{session_id}:{server_secret}".encode()).digest()


def make_token_id(session_key: bytes, value: str) -> str:
    """token_id = first TOKEN_ID_LEN hex chars of HMAC-SHA256(session_key,
    NFKC-normalized value). Same value -> same token within a session;
    different session_key -> different token for the same value.

    Unchanged from the fixed-width scheme: only the SURFACE format around
    this id varies by type now, never the id derivation itself."""
    normalized = unicodedata.normalize("NFKC", value)
    digest = hmac.new(session_key, normalized.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:TOKEN_ID_LEN]


def format_token(token_id: str, label: str) -> str:
    """Type-labeled surface placeholder, e.g.
    format_token('a1b2c3d4e5', 'EMAIL') -> '<EMAIL_PII_a1b2c3d4e5>'.

    `label` is a SpanLabel value (e.g. 'EMAIL', 'CREDIT_CARD'). The 10-hex
    id is embedded verbatim so rehydration can reverse by it."""
    return f"<{label}_PII_{token_id}>"


def make_token(session_key: bytes, value: str, label: str = "MISC") -> str:
    """Convenience: derive the id and format the placeholder in one step,
    e.g. make_token(k, 'a@b.com', 'EMAIL') -> '<EMAIL_PII_a1b2c3d4e5>'."""
    return format_token(make_token_id(session_key, value), label)


# The complete placeholder: `<{LABEL}_PII_{10hex}>`. The label may itself
# contain underscores (CREDIT_CARD, GOV_ID, IP_ADDRESS, DATE_TIME); the
# `_PII_` sentinel + fixed 10-hex id disambiguate the backtrack. The single
# capture group is the token_id -- the only thing rehydration needs.
TOKEN_RE = re.compile(r"<[A-Z][A-Z_]*_PII_([0-9a-f]{10})>")

# Longest possible placeholder across every SpanLabel. gateway/streaming.py
# holds back this-minus-one characters so an incomplete token of ANY type is
# always kept out of the flush region (see streaming.py). Derived from the
# enum so it stays correct if labels change.
MAX_TOKEN_LEN = max(len(format_token("0" * TOKEN_ID_LEN, label.value)) for label in SpanLabel)
