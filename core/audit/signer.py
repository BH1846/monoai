"""Per-record Ed25519 signing (G13): distinct from evidence.py's
whole-bundle export signature -- this signs every individual chained
record at append time, so a single tampered or replayed JSONL line is
independently detectable without needing the full log or a fresh
export.

Key material: MONOAI_AUDIT_SIGN_KEY, if set, seeds the signing key
(any string; hashed to 32 bytes so it doesn't need to be raw key
material). Otherwise falls back to a deterministic derivation of
SESSION_TOKEN_SECRET, so a signing key always exists the moment
MONOAI_AUDIT_SIGN=true without provisioning a second secret. This is a
process-local deterministic derivation (not Valkey-stored like
audit/signing.py's evidence-export key) -- every gateway instance
sharing the same secret produces the same signing key, which is
required for a multi-worker deployment's chain to verify consistently.
"""
from __future__ import annotations

import hashlib

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from contracts.audit import AuditRecord


def _seed_from_secret(secret: str) -> bytes:
    return hashlib.sha256(secret.encode("utf-8")).digest()


def load_signing_key(audit_sign_key: str | None, session_token_secret: str) -> SigningKey:
    secret = audit_sign_key or session_token_secret
    return SigningKey(_seed_from_secret(secret))


def sign_record(record: AuditRecord, signing_key: SigningKey) -> str:
    """Signs the record's own chain hash (compute_hash already covers
    every other field, including prev_hash) -- hex-encoded Ed25519
    signature. Requires the hash to already be computed (i.e. call
    after AuditChain has assigned `record.hash`, before writing)."""
    if record.hash is None:
        raise ValueError("cannot sign a record before its chain hash is computed")
    return signing_key.sign(record.hash.encode("utf-8")).signature.hex()


def verify_record(record: AuditRecord, public_key_hex: str) -> bool:
    if record.hash is None or record.signature is None:
        return False
    verify_key = VerifyKey(bytes.fromhex(public_key_hex))
    try:
        verify_key.verify(record.hash.encode("utf-8"), bytes.fromhex(record.signature))
        return True
    except BadSignatureError:
        return False
