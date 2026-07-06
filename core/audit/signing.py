"""Ed25519 signing keypair management for evidence export -- G10.

Mirrors core/vault/crypto.py's Valkey-backed load-or-create pattern
(atomic create-if-absent via SET NX), just for a signing key instead of
an encryption keypair.
"""
from __future__ import annotations

from nacl.signing import SigningKey

_DEFAULT_KEY_NAME = "monoai:audit:signing_key"


def load_or_create_signing_key(client, key_name: str = _DEFAULT_KEY_NAME) -> SigningKey:
    existing = client.get(key_name)
    if existing is not None:
        return SigningKey(existing)

    candidate = SigningKey.generate()
    created = client.set(key_name, bytes(candidate), nx=True)
    if created:
        return candidate
    winner = client.get(key_name)
    if winner is None:
        raise RuntimeError(f"failed to load or create audit signing key {key_name!r}")
    return SigningKey(winner)
