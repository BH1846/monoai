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

TOKEN_ID_LEN = 10 (hex chars) is deliberate: it keeps the bracketed token
`[PII_TOKEN_xxxxxxxxxx]` at a fixed width of exactly 22 characters, which
is what lets gateway/streaming.py's sliding-window rehydrator use a
closed-form holdback size instead of a regex partial-match state machine.
"""
from __future__ import annotations

import hashlib
import hmac
import unicodedata

TOKEN_ID_LEN = 10
TOKEN_PREFIX = "PII_TOKEN_"


def derive_session_key(session_id: str, server_secret: str) -> bytes:
    """One per-deployment secret (SESSION_TOKEN_SECRET) + the session_id ->
    a session-scoped HMAC key. Cheap to recompute; never persisted."""
    return hashlib.sha256(f"{session_id}:{server_secret}".encode()).digest()


def make_token_id(session_key: bytes, value: str) -> str:
    """token_id = first TOKEN_ID_LEN hex chars of HMAC-SHA256(session_key,
    NFKC-normalized value). Same value -> same token within a session;
    different session_key -> different token for the same value."""
    normalized = unicodedata.normalize("NFKC", value)
    digest = hmac.new(session_key, normalized.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:TOKEN_ID_LEN]


def make_token(session_key: bytes, value: str) -> str:
    """The full bracketed placeholder, e.g. '[PII_TOKEN_a1b2c3d4e5]'."""
    return f"[{TOKEN_PREFIX}{make_token_id(session_key, value)}]"
