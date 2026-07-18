"""End-to-end virtual-key federation across two real gateway apps.

Proves the whole loop:
  * a key created on the ORIGIN appears in the MANAGER's Users tab (list_keys),
    tagged origin_gateway, WITHOUT becoming valid for auth on the manager;
  * a revoke made on the origin forwards and flips the manager's copy;
  * a revoke made ON THE MANAGER of a forwarded key propagates BACK to the
    origin and actually deactivates the key there;
  * idempotent ingest (at-least-once retries don't duplicate/loop).
"""
from __future__ import annotations

import httpx
from api import admin as admin_api
from audit.forward_queue import SqliteForwardQueue
from audit_dedupe import SqliteIngestDedupe
from auth.middleware import AuthenticationError, authenticate
from auth.store import SqliteKeyStore
from fastapi import FastAPI
from fastapi.testclient import TestClient
from key_forwarder import KeyEventForwarder

SHARED = "shared-federation-key"


def _make_gateway(tmp_path, name: str, *, gateway_id: str, callback_url: str | None) -> FastAPI:
    app = FastAPI()
    app.include_router(admin_api.router)

    class _Settings:
        admin_key = SHARED
        # gateway_id / gateway_callback_url are read by admin._forward_key_event
        pass

    _Settings.gateway_id = gateway_id
    _Settings.gateway_callback_url = callback_url

    app.state.settings = _Settings()
    app.state.key_store = SqliteKeyStore(str(tmp_path / f"{name}_keys.sqlite"))
    app.state.key_ingest_dedupe = SqliteIngestDedupe(str(tmp_path / f"{name}_kingest.sqlite"))
    app.state.key_revoke_ingest_dedupe = SqliteIngestDedupe(str(tmp_path / f"{name}_krevingest.sqlite"))
    return app


def _headers() -> dict:
    return {"Authorization": f"Bearer {SHARED}"}


def test_full_bidirectional_key_federation(tmp_path):
    # --- two gateways: Rahul's (origin) and the manager -----------------
    manager = _make_gateway(tmp_path, "manager", gateway_id="manager-gw", callback_url=None)
    origin = _make_gateway(tmp_path, "origin", gateway_id="rahul-gateway", callback_url="http://rahul")

    manager_client = TestClient(manager)
    origin_client = TestClient(origin)

    # Origin forwards its key events to the manager's /keys/ingest.
    origin.state.key_forwarder = KeyEventForwarder(
        admin_key=SHARED, queue=SqliteForwardQueue(str(tmp_path / "origin_fwd.sqlite")),
        default_url="http://manager/v1/admin/keys/ingest",
        start_worker=False, transport=manager_client._transport,
    )
    # Manager pushes reverse revokes to the origin's callback URL. A little
    # router sends each event to whichever gateway its _target_url names.
    def route_to_origin(request: httpx.Request) -> httpx.Response:
        # rewrite http://rahul/... -> the origin ASGI app
        sub = httpx.Request(request.method, str(request.url).replace("http://rahul", "http://origin"),
                            headers=request.headers, content=request.content)
        return origin_client._transport.handle_request(sub)

    manager.state.key_reverse_forwarder = KeyEventForwarder(
        admin_key=SHARED, queue=SqliteForwardQueue(str(tmp_path / "manager_rev.sqlite")),
        default_url=None, start_worker=False, transport=httpx.MockTransport(route_to_origin),
    )

    try:
        # === 1. create a key on the origin -> forwards to manager ===
        r = origin_client.post("/v1/admin/keys", json={"team_id": "rahul-team"}, headers=_headers())
        assert r.status_code == 200
        raw_key = r.json()["key"]
        key_id = r.json()["key_id"]

        assert origin.state.key_forwarder.drain_once() == 1  # deliver the "created" event

        # Manager's Users tab now shows Rahul's key, tagged + NOT auth-valid.
        keys = manager_client.get("/v1/admin/keys", headers=_headers()).json()["keys"]
        assert [k["key_id"] for k in keys] == [key_id]
        assert keys[0]["origin_gateway"] == "rahul-gateway"

        # === 2. the forwarded key must NOT authenticate on the manager ===
        # (decision B: visibility only). It DOES still authenticate on origin.
        try:
            authenticate(f"Bearer {raw_key}", manager.state.key_store)
            assert False, "forwarded key must not authenticate on the manager"
        except AuthenticationError:
            pass
        assert authenticate(f"Bearer {raw_key}", origin.state.key_store).key_id == key_id

        # === 3. revoke ON THE MANAGER -> propagates back to the origin ===
        r = manager_client.delete(f"/v1/admin/keys/{key_id}", headers=_headers())
        assert r.status_code == 200
        assert r.json()["propagated"] is True
        # Manager's copy is optimistically revoked immediately.
        assert manager.state.key_store.get_by_id(key_id).active is False

        # Deliver the reverse revoke to the origin.
        assert manager.state.key_reverse_forwarder.drain_once() == 1
        # The key is now actually deactivated on the ORIGIN too.
        assert origin.state.key_store.get_by_id(key_id).active is False
        # And it no longer authenticates on the origin.
        try:
            authenticate(f"Bearer {raw_key}", origin.state.key_store)
            assert False, "revoked key must not authenticate on the origin"
        except AuthenticationError:
            pass
    finally:
        origin.state.key_forwarder.close()
        manager.state.key_reverse_forwarder.close()


def test_origin_side_revoke_forwards_and_flips_manager_copy(tmp_path):
    manager = _make_gateway(tmp_path, "manager", gateway_id="manager-gw", callback_url=None)
    origin = _make_gateway(tmp_path, "origin", gateway_id="rahul-gateway", callback_url="http://rahul")
    manager_client = TestClient(manager)
    origin.state.key_forwarder = KeyEventForwarder(
        admin_key=SHARED, queue=SqliteForwardQueue(str(tmp_path / "origin_fwd.sqlite")),
        default_url="http://manager/v1/admin/keys/ingest",
        start_worker=False, transport=manager_client._transport,
    )
    try:
        origin_client = TestClient(origin)
        key_id = origin_client.post("/v1/admin/keys", json={}, headers=_headers()).json()["key_id"]
        origin.state.key_forwarder.drain_once()  # created

        origin_client.delete(f"/v1/admin/keys/{key_id}", headers=_headers())  # revoke locally
        assert origin.state.key_forwarder.drain_once() == 1  # revoked event

        # Manager's mirrored copy is now inactive too.
        assert manager.state.key_store.get_by_id(key_id).active is False
    finally:
        origin.state.key_forwarder.close()


def test_keys_ingest_is_idempotent_and_requires_admin(tmp_path):
    manager = _make_gateway(tmp_path, "manager", gateway_id="manager-gw", callback_url=None)
    client = TestClient(manager)

    event = {
        "event_id": "ev-dup", "event_type": "created", "gateway_id": "rahul-gateway",
        "callback_url": "http://rahul", "key_id": "vk_dup",
        "key": {"key_id": "vk_dup", "key_hash": "a" * 64, "policy_id": "default"},
    }
    # no auth -> 401
    assert client.post("/v1/admin/keys/ingest", json=event).status_code == 401

    r1 = client.post("/v1/admin/keys/ingest", json=event, headers=_headers())
    assert r1.status_code == 200 and r1.json()["duplicate"] is False
    r2 = client.post("/v1/admin/keys/ingest", json=event, headers=_headers())
    assert r2.status_code == 200 and r2.json()["duplicate"] is True

    keys = manager.state.key_store.list_keys()
    assert len([k for k in keys if k.key_id == "vk_dup"]) == 1  # ingested once


def test_manager_revoke_without_callback_url_reports_not_propagated(tmp_path):
    """A forwarded key whose origin advertised no callback URL: the manager
    revokes its local copy but honestly reports it couldn't reach the origin."""
    manager = _make_gateway(tmp_path, "manager", gateway_id="manager-gw", callback_url=None)
    manager.state.key_reverse_forwarder = KeyEventForwarder(
        admin_key=SHARED, queue=SqliteForwardQueue(str(tmp_path / "rev.sqlite")),
        default_url=None, start_worker=False, transport=httpx.MockTransport(lambda r: httpx.Response(200)),
    )
    client = TestClient(manager)
    try:
        # ingest a forwarded key with NO callback_url
        client.post("/v1/admin/keys/ingest", headers=_headers(), json={
            "event_id": "ev1", "event_type": "created", "gateway_id": "rahul-gateway",
            "callback_url": None, "key_id": "vk_nocb",
            "key": {"key_id": "vk_nocb", "key_hash": "b" * 64, "policy_id": "default"},
        })
        r = client.delete("/v1/admin/keys/vk_nocb", headers=_headers())
        assert r.status_code == 200
        assert r.json()["propagated"] is False
        assert manager.state.key_store.get_by_id("vk_nocb").active is False  # local copy still revoked
    finally:
        manager.state.key_reverse_forwarder.close()
