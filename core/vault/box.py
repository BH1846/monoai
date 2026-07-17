"""Authenticated agent<->manager channel crypto (manager/agent split).

Uses libsodium's crypto_box (X25519 + XSalsa20-Poly1305) via PyNaCl's
`Box` -- the SAME crypto stack the vault already depends on (core/vault/
crypto.py), NO new dependency. Deliberately NOT `SealedBox`: an agent
sealing to the manager must be *authenticated*, so /ingest can verify the
message really came from the agent whose pubkey it has on file. SealedBox
gives anonymous-sender confidentiality only and cannot do that.

This module is intentionally free of any Valkey / master-key coupling: it
takes raw key material as hex and does nothing else. That is what lets the
standalone agent import it without ever touching the manager's vault master
keypair -- the agent only ever holds its OWN private key and the manager's
public key.
"""
from __future__ import annotations

from nacl.public import Box, PrivateKey, PublicKey


def generate_keypair() -> tuple[str, str]:
    """Fresh X25519 keypair. Returns (private_key_hex, public_key_hex).

    The agent calls this once on first run; the private key never leaves
    the host it was generated on.
    """
    sk = PrivateKey.generate()
    return sk.encode().hex(), sk.public_key.encode().hex()


def public_key_of(private_key_hex: str) -> str:
    """Derive the public key (hex) from a private key (hex)."""
    return PrivateKey(bytes.fromhex(private_key_hex)).public_key.encode().hex()


def seal(sender_private_key_hex: str, recipient_public_key_hex: str, plaintext: str) -> tuple[str, str]:
    """Encrypt+authenticate `plaintext` from sender to recipient.

    Returns (nonce_hex, ciphertext_hex). A fresh random nonce is generated
    per call (PyNaCl default), so the same plaintext never encrypts to the
    same ciphertext twice.
    """
    box = Box(PrivateKey(bytes.fromhex(sender_private_key_hex)), PublicKey(bytes.fromhex(recipient_public_key_hex)))
    encrypted = box.encrypt(plaintext.encode("utf-8"))
    return encrypted.nonce.hex(), encrypted.ciphertext.hex()


def open_sealed(
    recipient_private_key_hex: str, sender_public_key_hex: str, nonce_hex: str, ciphertext_hex: str
) -> str:
    """Verify+decrypt a message from sender to recipient.

    Raises nacl.exceptions.CryptoError if authentication fails -- i.e. the
    message was tampered with or was NOT sealed by the holder of the private
    key matching `sender_public_key_hex`. /ingest relies on that: an
    envelope claiming to be from agent X but not actually sealed with X's
    private key fails here and is rejected.
    """
    box = Box(PrivateKey(bytes.fromhex(recipient_private_key_hex)), PublicKey(bytes.fromhex(sender_public_key_hex)))
    return box.decrypt(bytes.fromhex(ciphertext_hex), bytes.fromhex(nonce_hex)).decode("utf-8")
