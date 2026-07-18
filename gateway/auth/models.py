from __future__ import annotations

import time

from pydantic import BaseModel, Field


class VirtualKey(BaseModel):
    key_id: str  # "vk_" + 12 hex of sha256(raw_key) -- safe to log/cite
    key_hash: str  # full sha256(raw_key) hex -- raw key itself never stored
    team_id: str | None = None
    policy_id: str = "default"
    model_allowlist: list[str] | None = None
    budget_usd_monthly: float | None = None
    budget_usd_spent: float = 0.0
    rate_limit_rps: float = 5.0
    rate_limit_burst: int = 20
    active: bool = True
    created_at: float = Field(default_factory=time.time)
    revoked_at: float | None = None
    # -- federation provenance (key forwarding) --
    # None for a key created on THIS gateway. Set when the key was forwarded
    # in from a peer gateway instance (audit-forwarding sibling feature):
    #   origin_gateway      -- which instance created it (Users-tab attribution)
    #   origin_callback_url -- that instance's reachable base URL, so a
    #                          manager-side revoke can propagate BACK to it.
    # A forwarded key is visibility-only: authenticate() refuses it (see
    # gateway/auth/middleware.py) so a peer's key never logs into this gateway.
    origin_gateway: str | None = None
    origin_callback_url: str | None = None
