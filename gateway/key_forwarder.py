"""KeyEventForwarder: durable, background delivery of key-federation events.

This is the virtual-key sibling of core/audit/sinks.py's ForwardingSink,
kept as a SEPARATE, self-contained class rather than refactoring ForwardingSink
into a shared base -- the audit forwarding path is deliberately not touched.
It reuses core/audit/forward_queue.py's SqliteForwardQueue unchanged (that
store is payload-agnostic: an id string + opaque JSON).

Used in BOTH directions:
  * forward  (origin -> manager): `default_url` is the manager's ingest URL;
    every event goes there.
  * reverse  (manager -> origin): the target is PER-EVENT (each key was
    forwarded in from a different origin), carried as `_target_url` inside
    the payload; `default_url` is unused.

## Same guarantees as audit forwarding

`enqueue()` does NO network I/O and never raises -- it runs on the admin
request path (key create/revoke), so a peer being down must not slow or break
the actual key operation, which has already committed locally. A background
thread drains the durable queue oldest-first, STOPS at the first failure to
preserve order, and removes an event only on a confirmed 2xx. Delivery is
at-least-once, so the receiving endpoint dedupes on event_id.
"""
from __future__ import annotations

import json
import logging
import threading
import time

import httpx

logger = logging.getLogger(__name__)


class KeyEventForwarder:
    def __init__(
        self,
        admin_key: str,
        queue,
        default_url: str | None = None,
        interval_s: float = 30.0,
        timeout: float = 5.0,
        batch_size: int = 100,
        start_worker: bool = True,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._default_url = default_url
        self._queue = queue
        self._client = httpx.Client(
            timeout=timeout,
            headers={"Authorization": f"Bearer {admin_key}", "Content-Type": "application/json"},
            transport=transport,
        )
        self._interval_s = interval_s
        self._batch_size = batch_size
        self._wake = threading.Event()
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None
        if start_worker:
            self._thread = threading.Thread(target=self._run, name="key-forwarder", daemon=True)
            self._thread.start()

    # -- request path (fast, never raises) ---------------------------------

    def enqueue(self, event_id: str, payload: dict) -> None:
        """Durably queue one event + wake the worker. `payload` may carry a
        `_target_url` for per-event routing (reverse direction); otherwise the
        forwarder's default_url is used. No network I/O, never raises: the key
        op already committed locally, so a forwarding failure is not fatal."""
        try:
            self._queue.append(event_id, json.dumps(payload), time.time())
            self._wake.set()
        except Exception:  # noqa: BLE001 -- forwarding must never break the key op
            logger.warning("failed to enqueue key event for forwarding", exc_info=True)

    # -- background worker -------------------------------------------------

    def _run(self) -> None:  # pragma: no cover - exercised via drain_once in tests
        while not self._stopped.is_set():
            try:
                self.drain_once()
            except Exception:  # noqa: BLE001 -- the worker must never die
                logger.warning("key forwarding sweep failed", exc_info=True)
            self._wake.wait(self._interval_s)
            self._wake.clear()

    def drain_once(self) -> int:
        """Deliver queued events oldest-first; stop at the first failure so
        order is preserved. Returns the number delivered."""
        delivered = 0
        while not self._stopped.is_set():
            batch = self._queue.peek_batch(self._batch_size)
            if not batch:
                break
            for item in batch:
                if not self._deliver(item.payload_json):
                    return delivered  # keep order: don't skip past a failure
                self._queue.ack([item.seq])
                delivered += 1
            if len(batch) < self._batch_size:
                break
        return delivered

    def _deliver(self, payload_json: str) -> bool:
        """POST one event to its target. True only on a confirmed 2xx."""
        try:
            data = json.loads(payload_json)
        except json.JSONDecodeError:
            logger.warning("dropping unparseable queued key event")
            return True  # can never succeed; drop rather than poison the queue
        target = data.pop("_target_url", None) or self._default_url
        if not target:
            # Undeliverable (reverse event with no origin callback URL). Drop
            # with a warning instead of blocking the queue forever.
            logger.warning("dropping key event with no target url (origin has no callback url)")
            return True
        try:
            resp = self._client.post(target, content=json.dumps(data))
        except httpx.HTTPError:
            return False
        return 200 <= resp.status_code < 300

    def close(self) -> None:
        self._stopped.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._client.close()
        close = getattr(self._queue, "close", None)
        if close is not None:
            close()
