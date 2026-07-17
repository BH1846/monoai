"""Agent identity: the agent's own X25519 keypair + the manager-issued
identifiers, persisted to the agent's local state dir.

HARD SECURITY BOUNDARY (from the build brief): the agent generates its
keypair on its OWN host and only ever holds (a) its own private key and
(b) the manager's public key. It NEVER has the manager's Valkey master
keypair or any vault key material. That is enforced structurally here: this
module uses core/vault/box.generate_keypair (raw libsodium, no Valkey) and
writes the private key to a local file with 0600 perms -- there is no code
path by which manager key material could reach it.

The private key is stored hex in identity.json alongside agent_id and the
manager pubkey. On a real deployment you would back this with an OS keystore
/ TPM; that (TEE attestation) is explicitly out of scope this pass and
flagged, not attempted.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from vault.box import generate_keypair, public_key_of

_IDENTITY_FILE = "identity.json"


@dataclass
class AgentIdentity:
    private_key: str  # hex, agent-only, never transmitted
    public_key: str  # hex, sent to manager at enroll
    agent_id: str | None = None  # assigned by manager on enroll
    manager_pubkey: str | None = None  # manager X25519 pubkey (hex), from enroll response
    policy_id: str = "default"

    @property
    def enrolled(self) -> bool:
        return self.agent_id is not None and self.manager_pubkey is not None


def _path(state_dir: str) -> Path:
    return Path(state_dir) / _IDENTITY_FILE


def load_or_create(state_dir: str, policy_id: str = "default") -> AgentIdentity:
    """Load existing identity, or mint a fresh keypair on first run. The
    private key never leaves this host."""
    Path(state_dir).mkdir(parents=True, exist_ok=True)
    p = _path(state_dir)
    if p.is_file():
        data = json.loads(p.read_text(encoding="utf-8"))
        return AgentIdentity(**data)

    priv, pub = generate_keypair()
    identity = AgentIdentity(private_key=priv, public_key=pub, policy_id=policy_id)
    save(state_dir, identity)
    return identity


def save(state_dir: str, identity: AgentIdentity) -> None:
    Path(state_dir).mkdir(parents=True, exist_ok=True)
    p = _path(state_dir)
    # 0600: the private key is the agent's whole identity; keep it readable
    # only by the owner.
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(identity.__dict__, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(p)
    # Sanity: the stored pubkey must actually derive from the stored privkey.
    assert public_key_of(identity.private_key) == identity.public_key
