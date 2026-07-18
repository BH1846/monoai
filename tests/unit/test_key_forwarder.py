"""KeyEventForwarder: the same non-blocking/durable/ordered guarantees as the
audit ForwardingSink, plus per-event target-URL routing (reverse direction)."""
from __future__ import annotations

import time

import httpx
from audit.forward_queue import SqliteForwardQueue
from key_forwarder import KeyEventForwarder


def _forwarder(tmp_path, handler, default_url="http://manager/v1/admin/keys/ingest", **kw) -> KeyEventForwarder:
    return KeyEventForwarder(
        admin_key="shared-key",
        queue=SqliteForwardQueue(str(tmp_path / "kfwd.sqlite")),
        default_url=default_url,
        start_worker=False,
        transport=httpx.MockTransport(handler),
        **kw,
    )


def test_enqueue_is_non_blocking_and_no_network(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    fwd = _forwarder(tmp_path, handler)
    try:
        t0 = time.monotonic()
        for i in range(20):
            fwd.enqueue(f"ev{i}", {"event_type": "created", "key_id": f"vk_{i}"})
        assert time.monotonic() - t0 < 0.5
        assert calls == []  # nothing delivered on the enqueue path
        assert fwd._queue.pending_count() == 20
    finally:
        fwd.close()


def test_enqueue_never_raises_on_broken_queue(tmp_path):
    class _Broken:
        def append(self, *a, **k):
            raise RuntimeError("disk full")

        def close(self):
            pass

    fwd = KeyEventForwarder(admin_key="k", queue=_Broken(), default_url="http://x", start_worker=False)
    try:
        fwd.enqueue("ev", {"key_id": "vk_1"})  # must not raise
    finally:
        fwd.close()


def test_delivers_to_default_url_with_auth(tmp_path):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200)

    fwd = _forwarder(tmp_path, handler)
    try:
        fwd.enqueue("ev1", {"event_type": "created", "key_id": "vk_1"})
        assert fwd.drain_once() == 1
        assert fwd._queue.pending_count() == 0
        assert str(seen[0].url) == "http://manager/v1/admin/keys/ingest"
        assert seen[0].headers["authorization"] == "Bearer shared-key"
    finally:
        fwd.close()


def test_per_event_target_url_overrides_default(tmp_path):
    """Reverse direction: each event names its own origin gateway."""
    targets = []

    def handler(request):
        targets.append(str(request.url))
        return httpx.Response(200)

    fwd = _forwarder(tmp_path, handler, default_url=None)
    try:
        fwd.enqueue("ev1", {"key_id": "vk_1", "_target_url": "http://rahul:8000/v1/admin/keys/revoke-ingest"})
        fwd.enqueue("ev2", {"key_id": "vk_2", "_target_url": "http://priya:8000/v1/admin/keys/revoke-ingest"})
        assert fwd.drain_once() == 2
        assert targets == [
            "http://rahul:8000/v1/admin/keys/revoke-ingest",
            "http://priya:8000/v1/admin/keys/revoke-ingest",
        ]
    finally:
        fwd.close()


def test_target_url_is_stripped_from_delivered_body(tmp_path):
    bodies = []

    def handler(request):
        import json
        bodies.append(json.loads(request.content))
        return httpx.Response(200)

    fwd = _forwarder(tmp_path, handler, default_url=None)
    try:
        fwd.enqueue("ev1", {"key_id": "vk_1", "gateway_id": "mgr", "_target_url": "http://rahul/x"})
        fwd.drain_once()
        assert "_target_url" not in bodies[0]  # internal routing field never sent
        assert bodies[0]["key_id"] == "vk_1"
    finally:
        fwd.close()


def test_failure_keeps_queued_and_preserves_order(tmp_path):
    delivered = []

    def handler(request):
        import json
        rid = json.loads(request.content)["key_id"]
        if rid == "vk_2":
            raise httpx.ConnectError("down")
        delivered.append(rid)
        return httpx.Response(200)

    fwd = _forwarder(tmp_path, handler)
    try:
        for i in range(1, 5):
            fwd.enqueue(f"ev{i}", {"key_id": f"vk_{i}"})
        assert fwd.drain_once() == 1  # vk_1 only; stops at vk_2
        assert delivered == ["vk_1"]
        assert fwd._queue.pending_count() == 3  # vk_2, vk_3, vk_4 retained in order
    finally:
        fwd.close()


def test_non_2xx_does_not_dequeue(tmp_path):
    def handler(request):
        return httpx.Response(500)

    fwd = _forwarder(tmp_path, handler)
    try:
        fwd.enqueue("ev1", {"key_id": "vk_1"})
        assert fwd.drain_once() == 0
        assert fwd._queue.pending_count() == 1
    finally:
        fwd.close()


def test_reconnect_replays_backlog(tmp_path):
    up = {"ok": False}

    def handler(request):
        if not up["ok"]:
            raise httpx.ConnectError("down")
        return httpx.Response(200)

    fwd = _forwarder(tmp_path, handler)
    try:
        for i in range(3):
            fwd.enqueue(f"ev{i}", {"key_id": f"vk_{i}"})
        assert fwd.drain_once() == 0
        up["ok"] = True
        assert fwd.drain_once() == 3
        assert fwd._queue.pending_count() == 0
    finally:
        fwd.close()
