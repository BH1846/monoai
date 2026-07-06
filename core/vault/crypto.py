"""Vault crypto: AES-256-GCM envelope encryption + libsodium sealed-box.

Ported from SENTINEL-2.0/pii_pipeline/vault.py's encryption primitives
(storage code split out into core/vault/storage/ — see DECISIONS.md). Same
Valkey-backed master keypair approach kept as-is: a hard dependency, no
on-disk fallback (per Phase 1 scope — key management itself isn't
redesigned this phase).

Per-entry: fresh random 32-byte AES-256-GCM data-encryption key (DEK), a
12-byte nonce, plaintext encrypted with AAD = "{session_id}:{token_id}"
(binds ciphertext to session+token so it can't be replayed under a
different token_id). The DEK is then sealed with a libsodium sealed box
(X25519 + XSalsa20-Poly1305) using the vault's public key; only the
private key (never leaves this module's owner) can unseal it back.
"""
from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from nacl.public import PrivateKey, PublicKey, SealedBox

_DEFAULT_KEY_NAME = "sentinel:pii_vault:master_key"


def _load_or_create_master_key(client, key_name: str) -> PrivateKey:
    """Atomically load-or-create a per-deployment X25519 keypair, persisted
    in Valkey/Redis (not on local disk). `client.set(..., nx=True)` makes
    creation race-safe across concurrent processes."""
    existing = client.get(key_name)
    if existing is not None:
        return PrivateKey(existing)

    candidate = PrivateKey.generate()
    created = client.set(key_name, bytes(candidate), nx=True)
    if created:
        return candidate
    # Lost the creation race -- someone else's key won, re-read it.
    winner = client.get(key_name)
    if winner is None:
        raise RuntimeError(f"failed to load or create vault master key {key_name!r}")
    return PrivateKey(winner)


class VaultCrypto:
    """Owns the master keypair; encrypts/decrypts individual vault entries.
    Stateless w.r.t. any particular entry -- safe to share across threads.
    """

    def __init__(self, valkey_client, key_name: str | None = None) -> None:
        self._key_name = key_name or _DEFAULT_KEY_NAME
        self._private_key = _load_or_create_master_key(valkey_client, self._key_name)
        self._public_key: PublicKey = self._private_key.public_key

    def encrypt(self, session_id: str, token_id: str, plaintext: str) -> tuple[bytes, bytes, bytes]:
        """Returns (nonce, ciphertext, sealed_dek)."""
        dek = os.urandom(32)
        nonce = os.urandom(12)
        aad = f"{session_id}:{token_id}".encode()
        ciphertext = AESGCM(dek).encrypt(nonce, plaintext.encode("utf-8"), aad)
        sealed_dek = SealedBox(self._public_key).encrypt(dek)
        return nonce, ciphertext, sealed_dek

    def decrypt(self, session_id: str, token_id: str, nonce: bytes, ciphertext: bytes, sealed_dek: bytes) -> str:
        dek = SealedBox(self._private_key).decrypt(sealed_dek)
        aad = f"{session_id}:{token_id}".encode()
        plaintext = AESGCM(dek).decrypt(nonce, ciphertext, aad)
        return plaintext.decode("utf-8")
