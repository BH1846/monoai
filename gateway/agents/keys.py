"""Manager-side X25519 keypair for the agent channel (manager/agent split).

Mirrors core/audit/signing.py's Valkey-backed load-or-create pattern (atomic
create-if-absent via SET NX), just for the manager's agent-channel encryption
keypair instead of an audit signing key.

This keypair is MANAGER-ONLY. Its public half is handed to agents in the
/enroll response so they can seal messages to the manager; its private half
never leaves the manager and is what /ingest uses to open sealed envelopes.
It is deliberately SEPARATE from the vault master keypair (core/vault/
crypto.py) -- the agent channel and the PII vault are different trust
domains and must not share key material.
"""
from __future__ import annotations

from nacl.public import PrivateKey

_DEFAULT_KEY_NAME = "monoai:agent_channel:manager_key"


def load_or_create_manager_keypair(client, key_name: str = _DEFAULT_KEY_NAME) -> PrivateKey:
    existing = client.get(key_name)
    if existing is not None:
        return PrivateKey(existing)

    candidate = PrivateKey.generate()
    created = client.set(key_name, bytes(candidate), nx=True)
    if created:
        return candidate
    winner = client.get(key_name)
    if winner is None:
        raise RuntimeError(f"failed to load or create manager agent-channel key {key_name!r}")
    return PrivateKey(winner)
