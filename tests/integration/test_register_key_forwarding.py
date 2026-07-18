"""Regression: a key created via self-serve /v1/auth/register must federate
to the manager exactly like an admin-created one.

This gap existed because the earlier key-federation tests only exercised the
admin path (api/admin.py), while /v1/auth/register calls create_key()
directly -- so self-registered users produced ZERO rows in the forward queue.
"""
from __future__ import annotations

import httpx
from api import auth as auth_api
from audit.forward_queue import SqliteForwardQueue
from auth.store import SqliteKeyStore
from fastapi import FastAPI
from fastapi.testclient import TestClient
from key_forwarder import KeyEventForwarder


class _UserAccountStore:
    """Minimal stand-in for SqliteUserAccountStore: just enough for register."""

    def __init__(self) -> None:
        self._by_email: dict[str, object] = {}

    def exists(self, email: str) -> bool:
        return email in self._by_email

    def register(self, email: str, password: str, key_id: str, raw_key: str):
        from types import SimpleNamespace
        acct = SimpleNamespace(email=email, key_id=key_id, virtual_key=raw_key)
        self._by_email[email] = acct
        return acct


def _make_gateway(tmp_path, *, with_forwarder: bool) -> FastAPI:
    app = FastAPI()
    app.include_router(auth_api.router)

    class _Settings:
        gateway_id = "rahul-gateway"
        gateway_callback_url = "http://rahul"
        self_serve_budget_usd_monthly = 20.0

    app.state.settings = _Settings()
    app.state.key_store = SqliteKeyStore(str(tmp_path / "keys.sqlite"))
    app.state.user_account_store = _UserAccountStore()
    app.state.key_forwarder = None
    if with_forwarder:
        app.state.key_forwarder = KeyEventForwarder(
            admin_key="shared-key",
            queue=SqliteForwardQueue(str(tmp_path / "kfwd.sqlite")),
            default_url="http://manager/v1/admin/keys/ingest",
            start_worker=False,
            transport=httpx.MockTransport(lambda r: httpx.Response(200)),
        )
    return app


def test_register_enqueues_key_forward_event(tmp_path):
    app = _make_gateway(tmp_path, with_forwarder=True)
    client = TestClient(app)
    try:
        r = client.post("/v1/auth/register", json={"email": "rahul@example.com", "password": "hunter2!!"})
        assert r.status_code == 200, r.text
        key_id = r.json()["key_id"]

        # The whole point: the self-serve key landed in the forward queue.
        forwarder = app.state.key_forwarder
        assert forwarder._queue.pending_count() == 1
        (queued,) = forwarder._queue.peek_batch(10)
        import json
        event = json.loads(queued.payload_json)
        assert event["event_type"] == "created"
        assert event["gateway_id"] == "rahul-gateway"
        assert event["key_id"] == key_id
        assert event["key"]["key_id"] == key_id
        assert event["key"]["team_id"] == "rahul@example.com"  # self-serve keys carry the email
    finally:
        app.state.key_forwarder.close()


def test_register_succeeds_when_forwarding_not_configured(tmp_path):
    """Fail-open: a non-forwarding gateway (key_forwarder is None) must still
    let users sign up."""
    app = _make_gateway(tmp_path, with_forwarder=False)
    client = TestClient(app)
    r = client.post("/v1/auth/register", json={"email": "solo@example.com", "password": "hunter2!!"})
    assert r.status_code == 200, r.text
    assert r.json()["key_id"].startswith("vk_")


def test_register_still_succeeds_if_enqueue_raises(tmp_path):
    """Fail-open: even if forwarding blows up, registration must not fail."""
    app = _make_gateway(tmp_path, with_forwarder=False)

    class _BoomForwarder:
        def enqueue(self, *a, **k):
            raise RuntimeError("queue on fire")

    app.state.key_forwarder = _BoomForwarder()
    client = TestClient(app)
    # forward_key_event -> forwarder.enqueue swallows the error internally;
    # registration returns 200 regardless.
    r = client.post("/v1/auth/register", json={"email": "boom@example.com", "password": "hunter2!!"})
    assert r.status_code == 200, r.text
