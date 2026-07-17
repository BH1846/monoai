"""ForwardingSink + FanoutSink.

The load-bearing guarantees, in order of how much they'd hurt to get wrong:

  1. write() NEVER blocks on the network and NEVER raises -- AuditChain.append()
     runs inline on the chat request path, so a dead manager must not cost a
     live request a single millisecond.
  2. Nothing is dropped: a failed delivery leaves the record queued.
  3. Only a confirmed 2xx dequeues a record.
  4. Order is preserved -- a failure stops the drain rather than skipping ahead.
"""
from __future__ import annotations

import time

import httpx
import pytest
from audit.forward_queue import SqliteForwardQueue
from audit.sinks import FanoutSink, ForwardingSink
from contracts.audit import AuditRecord


def _record(**overrides) -> AuditRecord:
    data = dict(
        ts=1.0, request_id="r1", session_id="s1", event="completed",
        policy_id="default", policy_version="sha256:abc",
    )
    data.update(overrides)
    return AuditRecord(**data)


def _sink(tmp_path, handler, **kw) -> ForwardingSink:
    """A ForwardingSink pointed at a mock manager via an injected transport
    (so the real auth/header wiring is still exercised), with the background
    worker OFF so tests drive drain_once() deterministically."""
    return ForwardingSink(
        url="http://manager/v1/admin/audit/ingest",
        admin_key="test-admin-key",
        queue=SqliteForwardQueue(str(tmp_path / "forward.sqlite")),
        gateway_id="rahul-gateway",
        start_worker=False,
        transport=httpx.MockTransport(handler),
        **kw,
    )


def test_write_enqueues_without_network_and_stamps_origin(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    sink = _sink(tmp_path, handler)
    try:
        sink.write(_record())
        # write() must not have touched the network at all.
        assert calls == []
        assert sink._queue.pending_count() == 1
        # ...and the queued copy carries this gateway's id.
        (queued,) = sink._queue.peek_batch(10)
        assert AuditRecord.model_validate_json(queued.payload_json).origin_gateway == "rahul-gateway"
    finally:
        sink.close()


def test_write_never_blocks_even_when_manager_hangs(tmp_path):
    """The request-path guarantee: a manager that hangs must not stall write()."""

    def handler(request):
        time.sleep(5.0)  # a manager that never answers
        return httpx.Response(200)

    sink = _sink(tmp_path, handler)
    try:
        t0 = time.monotonic()
        for _ in range(20):
            sink.write(_record())
        elapsed = time.monotonic() - t0
        assert elapsed < 0.5, f"write() blocked for {elapsed:.2f}s -- it must never do network I/O"
    finally:
        sink.close()


def test_write_never_raises_even_if_queue_is_broken(tmp_path):
    """Fail-open: forwarding must never break AuditChain.append()."""

    class _BrokenQueue:
        def append(self, *a, **k):
            raise RuntimeError("disk on fire")

        def close(self):
            pass

    sink = ForwardingSink(
        url="http://manager/x", admin_key="k", queue=_BrokenQueue(),
        gateway_id="g", start_worker=False,
    )
    try:
        sink.write(_record())  # must not raise
    finally:
        sink.close()


def test_failed_delivery_keeps_record_queued(tmp_path):
    def handler(request):
        raise httpx.ConnectError("manager down")

    sink = _sink(tmp_path, handler)
    try:
        sink.write(_record())
        assert sink.drain_once() == 0
        assert sink._queue.pending_count() == 1  # retained, not dropped
    finally:
        sink.close()


@pytest.mark.parametrize("status", [400, 401, 500, 503])
def test_non_2xx_does_not_dequeue(tmp_path, status):
    def handler(request):
        return httpx.Response(status)

    sink = _sink(tmp_path, handler)
    try:
        sink.write(_record())
        assert sink.drain_once() == 0
        assert sink._queue.pending_count() == 1
    finally:
        sink.close()


def test_successful_drain_dequeues_and_sends_auth_header(tmp_path):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"accepted": True})

    sink = _sink(tmp_path, handler)
    try:
        sink.write(_record())
        assert sink.drain_once() == 1
        assert sink._queue.pending_count() == 0
        assert seen[0].headers["authorization"] == "Bearer test-admin-key"
    finally:
        sink.close()


def test_reconnect_replays_backlog_in_order(tmp_path):
    """The whole point: buffer while down, sync in order once back."""
    up = {"ok": False}
    delivered: list[str] = []

    def handler(request):
        if not up["ok"]:
            raise httpx.ConnectError("manager down")
        delivered.append(AuditRecord.model_validate_json(request.content).request_id)
        return httpx.Response(200)

    sink = _sink(tmp_path, handler)
    try:
        for i in range(5):
            sink.write(_record(request_id=f"req-{i}"))
        assert sink.drain_once() == 0
        assert sink._queue.pending_count() == 5

        up["ok"] = True
        assert sink.drain_once() == 5
        assert sink._queue.pending_count() == 0
        assert delivered == ["req-0", "req-1", "req-2", "req-3", "req-4"]
    finally:
        sink.close()


def test_drain_stops_at_first_failure_to_preserve_order(tmp_path):
    """If record 2 can't be delivered, 3+ must NOT be sent ahead of it."""
    delivered: list[str] = []

    def handler(request):
        rid = AuditRecord.model_validate_json(request.content).request_id
        if rid == "req-2":
            raise httpx.ConnectError("flaky")
        delivered.append(rid)
        return httpx.Response(200)

    sink = _sink(tmp_path, handler)
    try:
        for i in range(5):
            sink.write(_record(request_id=f"req-{i}"))
        assert sink.drain_once() == 2  # 0 and 1 only
        assert delivered == ["req-0", "req-1"]
        assert sink._queue.pending_count() == 3  # 2,3,4 still queued, in order
        assert [
            AuditRecord.model_validate_json(q.payload_json).request_id
            for q in sink._queue.peek_batch(10)
        ] == ["req-2", "req-3", "req-4"]
    finally:
        sink.close()


def test_fanout_writes_primary_first_and_survives_a_broken_secondary():
    written: list[str] = []

    class _Primary:
        def write(self, record):
            written.append("primary")

    class _BrokenSecondary:
        def write(self, record):
            written.append("secondary")
            raise RuntimeError("peer exploded")

    class _ThirdSink:
        def write(self, record):
            written.append("third")

    fanout = FanoutSink([_Primary(), _BrokenSecondary(), _ThirdSink()])
    fanout.write(_record())  # must not raise
    assert written == ["primary", "secondary", "third"]


def test_fanout_primary_failure_still_raises():
    """Local audit durability stays fail-closed."""

    class _BrokenPrimary:
        def write(self, record):
            raise RuntimeError("disk full")

    fanout = FanoutSink([_BrokenPrimary()])
    with pytest.raises(RuntimeError):
        fanout.write(_record())
