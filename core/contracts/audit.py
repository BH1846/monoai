from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class AuditRecord(BaseModel):
    """Chain-ready even though hash-chain persistence/signing is wired up in
    core/audit (Step 6). Invariant #1 is held structurally here: there is no
    `text`/`value` field anywhere on this model — only labels, counts, ids,
    and timings.
    """

    record_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    prev_hash: str | None = None
    hash: str | None = None
    signature: str | None = None  # G13: Ed25519 sig over `hash`, set by AuditChain.append when signing is on
    ts: float
    request_id: str
    session_id: str
    # -- provenance (see audit/chain.py's _OMIT_WHEN_NONE) --
    # Both are None for a record this gateway generated itself on its own
    # request path, and set only when the record arrived from elsewhere.
    # Adding fields here is ONLY safe because _canonical_json omits them
    # when None -- see the warning in audit/chain.py before adding more.
    #
    # `agent_id`: ingested from an enrolled remote agent (agent/ split).
    # `origin_gateway`: forwarded in from a peer gateway instance whose
    # operator runs their own full Torqk stack (audit forwarding). Lets the
    # Audit Log tab tell "Rahul's box" apart from locally-generated records.
    agent_id: str | None = None
    origin_gateway: str | None = None
    virtual_key_id: str | None = None
    team_id: str | None = None
    event: Literal[
        "completed",
        "blocked",
        "provider_failure",
        "circuit_open",
        "auth_rejected",
        "budget_exhausted",
        "rate_limited",
    ]
    policy_id: str
    policy_version: str
    detector_versions: dict[str, str] = Field(default_factory=dict)
    pack_versions: dict[str, str] = Field(default_factory=dict)
    span_counts_by_label: dict[str, int] = Field(default_factory=dict)
    blocked_labels: list[str] = Field(default_factory=list)
    redacted_count: int = 0
    difficulty: str | None = None
    model_id: str | None = None
    provider: str | None = None
    fallback_chain_position: int | None = None
    circuit_state: str | None = None
    unresolved_tokens: list[str] = Field(default_factory=list)
    review_required: bool = False
    router_tier: str | None = None
    router_confidence: float | None = None
    router_rationale: str | None = None
    pii_sanitize_ms: float | None = None
    router_ms: float | None = None
    pii_rehydrate_ms: float | None = None
    output_scan_ms: float | None = None
    total_ms: float | None = None
    usage: dict[str, int] | None = None
    cost_usd: float | None = None
    stream: bool = False
    ttfb_ms: float | None = None
