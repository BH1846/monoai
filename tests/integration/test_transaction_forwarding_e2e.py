"""End-to-end session federation: a chat session recorded on a forwarding
instance appears in the MANAGER's per-user drill-down, with the raw prompt/
reply encrypted at every hop.

Proves:
  * a forwarded session lands in the manager's transaction_store and is
    readable there (correct text), tagged origin_gateway;
  * the raw prompt/reply is NEVER on the wire in plaintext (only Box-sealed);
  * it is at-rest encrypted on the manager (stored via the manager's own vault);
  * idempotent ingest (retry doesn't duplicate);
  * fail-open (manager down -> sessions stay queued, request unaffected).
"""
from __future__ import annotations

import json

import httpx
from api import admin as admin_api
from audit.forward_queue import SqliteForwardQueue
from audit_dedupe import SqliteIngestDedupe
from auth.transaction_store import SqliteTransactionStore
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nacl.public import PrivateKey
from transaction_forwarder import TransactionForwarder

SHARED = "shared-admin-key"
SECRET_PROMPT = "my SSN is 123-45-6789 and my card is 4111111111111111"
SECRET_REPLY = "Sure, I noted 123-45-6789 for you."


class _FakeRedis:
    def __init__(self):
        self._s = {}

    def get(self, k):
        return self._s.get(k)

    def set(self, k, v, nx=False):
        if nx and k in self._s:
            return False
        self._s[k] = v
        return True


def _crypto():
    from vault.crypto import VaultCrypto
    return VaultCrypto(_FakeRedis())


def _make_manager(tmp_path) -> FastAPI:
    app = FastAPI()
    app.include_router(admin_api.router)

    class _Settings:
        admin_key = SHARED
        gateway_id = "manager-gw"

    app.state.settings = _Settings()
    app.state.manager_agent_key = PrivateKey.generate()
    app.state.transaction_store = SqliteTransactionStore(_crypto(), str(tmp_path / "manager_txns.sqlite"))
    app.state.transaction_ingest_dedupe = SqliteIngestDedupe(str(tmp_path / "manager_txn_dedupe.sqlite"))
    return app


def _forwarder(tmp_path, manager_client, origin_crypto, **kw) -> TransactionForwarder:
    priv = PrivateKey.generate()
    return TransactionForwarder(
        crypto=origin_crypto,
        origin_private_key_hex=priv.encode().hex(),
        origin_public_key_hex=priv.public_key.encode().hex(),
        gateway_id="rahul-gateway",
        ingest_url="http://manager/v1/admin/transactions/ingest",
        pubkey_url="http://manager/v1/admin/federation/pubkey",
        admin_key=SHARED,
        queue=SqliteForwardQueue(str(tmp_path / "txn_fwd.sqlite")),
        start_worker=False,
        transport=manager_client._transport,
        **kw,
    )


def _record(fwd, request_id="req-1"):
    fwd.enqueue(
        request_id=request_id, session_id="sess-1", team_id="sanjay@torkq.comss",
        virtual_key_id="vk_abc", model="demo-model", status="redacted",
        redaction_rules=["GOV_ID", "CREDIT_CARD"], input_tokens=10, output_tokens=8, cost=0.001,
        original_prompt=SECRET_PROMPT, redacted_prompt="my SSN is [GOV_ID] and my card is [CREDIT_CARD]",
        llm_reply="Sure, I noted [GOV_ID] for you.", rehydrated_reply=SECRET_REPLY,
    )


def test_forwarded_session_appears_on_manager_with_correct_text(tmp_path):
    manager = _make_manager(tmp_path)
    mc = TestClient(manager)
    fwd = _forwarder(tmp_path, mc, _crypto())
    try:
        _record(fwd)
        assert fwd._queue.pending_count() == 1
        assert fwd.drain_once() == 1
        assert fwd._queue.pending_count() == 0

        # The manager can read the session for this user, with the real text.
        txns = manager.state.transaction_store.list_transactions(virtual_key_id="vk_abc")
        assert len(txns) == 1
        t = txns[0]
        assert t.original_prompt == SECRET_PROMPT
        assert t.rehydrated_reply == SECRET_REPLY
        assert t.origin_gateway == "rahul-gateway"
        assert t.session_id == "sess-1"
        assert t.redaction_rules == ["GOV_ID", "CREDIT_CARD"]
    finally:
        fwd.close()


def test_raw_text_never_on_the_wire_in_plaintext(tmp_path):
    manager = _make_manager(tmp_path)
    mc = TestClient(manager)

    captured = {}
    real = mc._transport

    def capture(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/transactions/ingest"):
            captured["body"] = request.content.decode("utf-8", "replace")
        return real.handle_request(request)

    fwd = _forwarder(tmp_path, mc, _crypto())
    fwd._client = httpx.Client(transport=httpx.MockTransport(capture),
                               headers={"Authorization": f"Bearer {SHARED}", "Content-Type": "application/json"})
    try:
        _record(fwd)
        assert fwd.drain_once() == 1
        body = captured["body"]
        # The secrets must NOT appear anywhere in the request body...
        assert "123-45-6789" not in body
        assert "4111111111111111" not in body
        assert SECRET_PROMPT not in body
        # ...only the sealed blob does.
        parsed = json.loads(body)
        assert parsed["sealed_text"]["ciphertext"]
        assert parsed["origin_gateway"] == "rahul-gateway"
    finally:
        fwd.close()


def test_stored_at_rest_encrypted_on_manager(tmp_path):
    """The manager persists the forwarded text via its OWN vault -- the raw
    strings must not be readable in the sqlite file."""
    manager = _make_manager(tmp_path)
    mc = TestClient(manager)
    fwd = _forwarder(tmp_path, mc, _crypto())
    try:
        _record(fwd)
        fwd.drain_once()
        raw_db = open(str(tmp_path / "manager_txns.sqlite"), "rb").read()
        assert b"123-45-6789" not in raw_db
        assert b"4111111111111111" not in raw_db
    finally:
        fwd.close()


def test_ingest_is_idempotent(tmp_path):
    manager = _make_manager(tmp_path)
    mc = TestClient(manager)
    fwd = _forwarder(tmp_path, mc, _crypto())
    try:
        _record(fwd, request_id="dup")
        assert fwd.drain_once() == 1
        # Re-enqueue the SAME request_id and deliver again -> manager dedupes.
        _record(fwd, request_id="dup")
        assert fwd.drain_once() == 1  # sender still gets a 2xx (duplicate) and dequeues
        assert len(manager.state.transaction_store.list_transactions(virtual_key_id="vk_abc")) == 1
    finally:
        fwd.close()


def test_ingest_requires_admin(tmp_path):
    manager = _make_manager(tmp_path)
    mc = TestClient(manager)
    r = mc.post("/v1/admin/transactions/ingest", json={"request_id": "x", "origin_gateway": "g",
                                                       "origin_pubkey": "00", "sealed_text": {"nonce": "", "ciphertext": ""}})
    assert r.status_code == 401


def test_fail_open_manager_down_keeps_sessions_queued(tmp_path):
    manager = _make_manager(tmp_path)
    mc = TestClient(manager)
    fwd = _forwarder(tmp_path, mc, _crypto())
    try:
        _record(fwd)
        # Manager unreachable: the pubkey fetch fails -> nothing delivered, all queued.
        def _down(request):
            raise httpx.ConnectError("down")
        fwd._client = httpx.Client(transport=httpx.MockTransport(_down))
        fwd._manager_pubkey = None
        assert fwd.drain_once() == 0
        assert fwd._queue.pending_count() == 1  # retained
    finally:
        fwd.close()
