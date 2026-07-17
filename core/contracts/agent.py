"""Wire contracts for the manager/agent split (Wazuh-style).

The manager is the existing gateway (vault, policy authoring, hash-chained
audit, enrollment authority). An *agent* is a separate, standalone process
running on ANOTHER host: it enrolls once, runs SENTINEL Tier 0 (regex/
secrets) + Tier 1 (ONNX NER) locally, buffers events when the manager is
unreachable, and syncs on reconnect.

Invariant #1 (no raw PII/text anywhere in the audit surface) is held
structurally here exactly as in contracts/audit.py: `AgentEventPayload`
carries only labels, counts, ids, and timings -- never the detected text.

All agent->manager traffic is sealed with an authenticated PyNaCl Box
(agent privkey + manager pubkey); see core/vault/box.py. `SealedEnvelope`
is the on-the-wire frame for /ingest.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Registry lifecycle. "enrolled" = keypair known, no heartbeat yet;
# "online" = heartbeat within the freshness window; "offline" = missed
# N beats; "revoked" = manually disabled, /ingest and /policy refused.
AgentStatus = Literal["enrolled", "online", "offline", "revoked"]


class AgentRecord(BaseModel):
    """One row in the manager's agent registry. `pubkey` is the agent's
    X25519 public key (hex); the manager NEVER holds the agent's private
    key -- it is generated on the agent host at enroll time and never
    leaves it."""

    agent_id: str
    pubkey: str  # agent X25519 public key, hex
    hostname: str
    status: AgentStatus = "enrolled"
    # `policy_id` the agent enforces; `policy_version` is the version the
    # manager last observed the agent holding (updated on /policy pull and
    # /heartbeat) -- compared against the manager's latest to detect drift.
    policy_id: str = "default"
    policy_version: str = ""
    last_seen: float | None = None
    last_sync: float | None = None
    enrolled_at: float
    revoked_at: float | None = None


class EnrollRequest(BaseModel):
    """POST /v1/agent/enroll body. `token` is the one-time enrollment
    secret minted by an admin; `pubkey` is the agent's freshly generated
    X25519 public key (hex)."""

    token: str
    pubkey: str
    hostname: str
    policy_id: str = "default"


class EnrollResponse(BaseModel):
    agent_id: str
    manager_pubkey: str  # manager X25519 public key (hex) -- agent seals to this
    policy_id: str
    policy_version: str


class SealedEnvelope(BaseModel):
    """On-the-wire frame for sealed agent->manager payloads (/ingest). The
    manager looks up the agent's known pubkey by `agent_id`, then opens the
    Box with (manager privkey, agent pubkey) -- which authenticates the
    sender, something an anonymous SealedBox could not do."""

    agent_id: str
    nonce: str  # hex
    ciphertext: str  # hex; a Box-encrypted JSON list[AgentEventPayload]


class AgentEventPayload(BaseModel):
    """The decrypted inner content of one buffered agent detection event.
    Mirrors the non-sensitive fields of contracts.audit.AuditRecord so the
    manager can fold it straight into the EXISTING hash-chained log. No
    `text`/`value` field -- invariant #1."""

    ts: float
    request_id: str
    session_id: str
    event: Literal["completed", "blocked"]
    policy_id: str
    policy_version: str
    detector_versions: dict[str, str] = Field(default_factory=dict)
    pack_versions: dict[str, str] = Field(default_factory=dict)
    span_counts_by_label: dict[str, int] = Field(default_factory=dict)
    blocked_labels: list[str] = Field(default_factory=list)
    redacted_count: int = 0
    pii_sanitize_ms: float | None = None


class IngestResponse(BaseModel):
    accepted: int
    last_hash: str | None = None


class HeartbeatRequest(BaseModel):
    agent_id: str
    policy_version: str  # version the agent currently holds/enforces
    last_sync: float | None = None  # ts of the agent's last successful /ingest


class HeartbeatResponse(BaseModel):
    status: AgentStatus
    policy_version: str  # manager's CURRENT latest for this agent's policy
    policy_stale: bool  # True if the agent should pull /policy (drift)
