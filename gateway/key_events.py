"""Wire models for virtual-key federation (sibling of audit forwarding).

A key created/revoked on one gateway is forwarded to a peer "manager"
gateway so it appears in the manager's Users tab, and a manager-side revoke
of a forwarded key is propagated BACK to the origin gateway so it actually
takes effect there. Both directions ride the same durable-queue + background-
retry machinery the audit forwarding pass built (core/audit/forward_queue.py,
gateway/audit_dedupe.py), reused unchanged.

`event_id` is the idempotency key (dedupe is per-EVENT, not per-key: a
`created` then a later `revoked` for the same key_id are distinct events, so
deduping on key_id would wrongly drop the revoke).
"""
from __future__ import annotations

import time
import uuid
from typing import Literal

from auth.models import VirtualKey
from pydantic import BaseModel, Field


class KeyForwardEvent(BaseModel):
    """origin -> manager. A virtual key was created or revoked locally; the
    manager reflects it into its own KeyStore (visibility-only)."""

    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    event_type: Literal["created", "revoked"]
    gateway_id: str  # the origin instance's id (-> VirtualKey.origin_gateway)
    # The origin's own reachable base URL, so a manager-side revoke can be
    # pushed back here. None if the origin didn't set MONOAI_GATEWAY_CALLBACK_URL
    # -> the key is visible on the manager but not remotely revocable.
    callback_url: str | None = None
    ts: float = Field(default_factory=time.time)
    key_id: str
    # Full key body, present for "created" so the manager can mirror the row.
    # Absent for "revoked" (only key_id is needed to flip active=0).
    key: VirtualKey | None = None


class KeyRevokeEvent(BaseModel):
    """manager -> origin (reverse). Apply a revoke to the origin's OWN
    KeyStore. The origin does NOT re-forward it (that would loop)."""

    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    key_id: str
    gateway_id: str  # the manager instance's id, for attribution/logging
    ts: float = Field(default_factory=time.time)
