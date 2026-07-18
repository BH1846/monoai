"""Shared virtual-key forwarding hook.

The one place a create/revoke event is enqueued to the peer manager. Both the
admin path (api/admin.py) and the self-serve registration path (api/auth.py)
call THIS function -- there is no second, parallel enqueue path -- so a key is
federated identically no matter how it was created.

Best-effort by contract: a no-op when this gateway isn't a forwarder
(app.state.key_forwarder is None), and never raises (enqueue itself swallows
errors). The key operation has already committed locally, so a forwarding
problem must never fail the request that triggered it.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from key_events import KeyForwardEvent

logger = logging.getLogger(__name__)


def forward_key_event(request: Request, event_type: str, key_id: str, key: Any = None) -> None:
    forwarder = getattr(request.app.state, "key_forwarder", None)
    if forwarder is None:
        return
    # Defence-in-depth fail-open: KeyEventForwarder.enqueue already swallows,
    # but wrap the whole hook so NOTHING about forwarding -- building the event
    # or a substitute forwarder -- can ever fail the request whose key op has
    # already committed locally (a forwarding problem must never block signup).
    try:
        settings = request.app.state.settings
        event = KeyForwardEvent(
            event_type=event_type, gateway_id=settings.gateway_id,
            callback_url=getattr(settings, "gateway_callback_url", None),
            key_id=key_id, key=key,
        )
        forwarder.enqueue(event.event_id, event.model_dump(mode="json"))
    except Exception:  # noqa: BLE001 -- forwarding is best-effort, never fatal
        logger.warning("failed to forward key %s event for %s", event_type, key_id, exc_info=True)
