"""End-to-end audit forwarding: a forwarding gateway's ForwardingSink drains
into a real manager app's POST /v1/admin/audit/ingest, and the forwarded
records land in the manager's OWN hash chain (no parallel store), verify()
passing, distinguishable by origin_gateway."""
from __future__ import annotations

import httpx
from api import admin as admin_api
from audit.chain import AuditChain, verify
from audit.forward_queue import SqliteForwardQueue
from audit.sinks import ForwardingSink, JsonlSink, read_jsonl
from audit_dedupe import SqliteIngestDedupe
from contracts.audit import AuditRecord
from fastapi import FastAPI
from fastapi.testclient import TestClient

ADMIN = "manager-admin-key"


def _record(**overrides) -> AuditRecord:
    data = dict(
        ts=1.0, request_id="r1", session_id="s1", event="completed",
        policy_id="default", policy_version="sha256:abc",
    )
    data.update(overrides)
    return AuditRecord(**data)


def _make_manager(tmp_path) -> FastAPI:
    app = FastAPI()
    app.include_router(admin_api.router)

    class _Settings:
        admin_key = ADMIN

    app.state.settings = _Settings()
    app.state._audit_path = str(tmp_path / "manager_audit.jsonl")
    app.state.audit_chain = AuditChain(JsonlSink(app.state._audit_path))
    app.state.audit_ingest_dedupe = SqliteIngestDedupe(str(tmp_path / "dedupe.sqlite"))
    return app


def _forwarder(tmp_path, manager_client: TestClient) -> ForwardingSink:
    # Route the ForwardingSink's httpx calls into the manager ASGI app via
    # TestClient (a sync httpx.Client bridging to ASGI).
    return ForwardingSink(
        url="http://manager/v1/admin/audit/ingest",
        admin_key=ADMIN,
        queue=SqliteForwardQueue(str(tmp_path / "forward.sqlite")),
        gateway_id="rahul-gateway",
        start_worker=False,
        transport=manager_client._transport,
    )


def test_forwarded_records_land_in_manager_chain_and_verify(tmp_path):
    app = _make_manager(tmp_path)
    client = TestClient(app)
    sink = _forwarder(tmp_path, client)
    try:
        # The manager first logs one of ITS OWN records...
        app.state.audit_chain.append(_record(request_id="manager-local"))
        # ...then a forwarding gateway ships three of its own.
        for i in range(3):
            sink.write(_record(request_id=f"rahul-{i}"))
        assert sink.drain_once() == 3
        assert sink._queue.pending_count() == 0

        records = read_jsonl(app.state._audit_path)
        assert [r.request_id for r in records] == ["manager-local", "rahul-0", "rahul-1", "rahul-2"]
        # Local vs forwarded is distinguishable in the log.
        assert [r.origin_gateway for r in records] == [None, "rahul-gateway", "rahul-gateway", "rahul-gateway"]
        # The mixed chain still verifies as one chain.
        assert verify(records)
    finally:
        sink.close()


def test_ingest_requires_admin_key(tmp_path):
    app = _make_manager(tmp_path)
    client = TestClient(app)
    r = client.post("/v1/admin/audit/ingest", json=_record(origin_gateway="x").model_dump(mode="json"))
    assert r.status_code == 401
    r = client.post(
        "/v1/admin/audit/ingest",
        json=_record(origin_gateway="x").model_dump(mode="json"),
        headers={"Authorization": "Bearer wrong"},
    )
    assert r.status_code == 401


def test_ingest_is_idempotent_on_duplicate_record_id(tmp_path):
    """At-least-once retry: the same record_id arriving twice must append
    once and be acknowledged (200) the second time."""
    app = _make_manager(tmp_path)
    client = TestClient(app)
    rec = _record(request_id="dup-test", origin_gateway="rahul-gateway")
    headers = {"Authorization": f"Bearer {ADMIN}"}

    r1 = client.post("/v1/admin/audit/ingest", json=rec.model_dump(mode="json"), headers=headers)
    assert r1.status_code == 200 and r1.json()["accepted"] is True and r1.json()["duplicate"] is False

    r2 = client.post("/v1/admin/audit/ingest", json=rec.model_dump(mode="json"), headers=headers)
    assert r2.status_code == 200 and r2.json()["duplicate"] is True

    records = read_jsonl(app.state._audit_path)
    assert len(records) == 1  # appended exactly once
    assert verify(records)


def test_ingest_rejects_record_without_origin(tmp_path):
    """A forwarded record must be attributable; an unstamped one is refused
    rather than silently filed as locally-generated."""
    app = _make_manager(tmp_path)
    client = TestClient(app)
    r = client.post(
        "/v1/admin/audit/ingest",
        json=_record().model_dump(mode="json"),  # origin_gateway=None
        headers={"Authorization": f"Bearer {ADMIN}"},
    )
    assert r.status_code == 400


def test_duplicate_retry_dequeues_cleanly_end_to_end(tmp_path):
    """Simulate a lost-response retry through the real sink: first delivery
    commits on the manager but the sender doesn't dequeue; the resend must
    get a 2xx (duplicate) so the queue drains rather than wedging forever."""
    app = _make_manager(tmp_path)
    client = TestClient(app)

    # A transport that commits the request to the manager but drops the FIRST
    # response, forcing the sink to retry.
    real = client._transport
    state = {"drop_next": True}

    def handler(request: httpx.Request) -> httpx.Response:
        resp = real.handle_request(request)
        if state["drop_next"]:
            state["drop_next"] = False
            raise httpx.ReadTimeout("response lost", request=request)
        return httpx.Response(resp.status_code, headers=resp.headers, content=resp.read())

    sink = ForwardingSink(
        url="http://manager/v1/admin/audit/ingest", admin_key=ADMIN,
        queue=SqliteForwardQueue(str(tmp_path / "forward.sqlite")),
        gateway_id="rahul-gateway", start_worker=False,
        transport=httpx.MockTransport(handler),
    )
    try:
        sink.write(_record(request_id="retry-me"))
        assert sink.drain_once() == 0        # first attempt: response lost
        assert sink._queue.pending_count() == 1
        assert sink.drain_once() == 1        # retry: manager says duplicate -> 200 -> dequeue
        assert sink._queue.pending_count() == 0

        records = read_jsonl(app.state._audit_path)
        assert [r.request_id for r in records] == ["retry-me"]  # appended exactly once
        assert verify(records)
    finally:
        sink.close()
