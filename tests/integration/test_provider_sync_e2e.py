"""End-to-end provider/model config sync: manager -> instance (downward).

Proves:
  * a forwarding instance PULLS the manager's providers/models and can
    resolve() a synced model (with the correct API key, opened from the Box-
    sealed blob and re-encrypted under the instance's own VaultCrypto);
  * API keys are never on the wire in plaintext (only sealed blobs);
  * manager-exclusive: the instance's local provider adds are refused;
  * live apply: a change on the manager shows up on the next poll, no restart;
  * fail-open: a manager that's down/broken leaves the instance's last-known
    registry intact.
"""
from __future__ import annotations

import json

import httpx
from api import admin as admin_api
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nacl.public import PrivateKey
from provider_sync import ProviderSyncClient
from providers.dynamic_router import DynamicProviderRouter
from providers.registry_store import SqliteProviderStore
from vault.box import generate_keypair

SHARED = "shared-admin-key"


class _FakeRedis:
    def __init__(self) -> None:
        self._s: dict = {}

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
    app.state.provider_store = SqliteProviderStore(_crypto(), str(tmp_path / "manager_providers.sqlite"))
    app.state.manager_agent_key = PrivateKey.generate()  # manager's Box identity
    # provider_sync absent on the manager -> local adds allowed there
    app.state.provider_sync = None
    return app


def _sync_client(tmp_path, manager_client: TestClient, store, router) -> ProviderSyncClient:
    priv, pub = generate_keypair()
    return ProviderSyncClient(
        sync_url="http://manager/v1/admin/providers/sync",
        admin_key=SHARED,
        instance_private_key_hex=priv,
        instance_public_key_hex=pub,
        gateway_id="rahul-gateway",
        store=store,
        dynamic_router=router,
        start_worker=False,
        transport=manager_client._transport,
    )


def _headers():
    return {"Authorization": f"Bearer {SHARED}"}


def test_instance_pulls_and_resolves_synced_model(tmp_path):
    manager = _make_manager(tmp_path)
    mc = TestClient(manager)

    # Manager admin configures Groq + a model (local on the manager).
    prov = mc.post("/v1/admin/providers", headers=_headers(), json={
        "name": "groq", "kind": "openai-compatible", "base_url": "https://api.groq.com/openai/v1",
        "api_key": "gsk_SUPERSECRET_KEY",
    }).json()
    mc.post("/v1/admin/models", headers=_headers(), json={
        "model_id": "demo-model", "provider_id": prov["provider_id"], "upstream_model": "llama-3.1-8b-instant",
    })

    # Instance side: empty registry + a poller pointed at the manager.
    inst_store = SqliteProviderStore(_crypto(), str(tmp_path / "inst_providers.sqlite"))
    inst_router = DynamicProviderRouter(inst_store)
    sync = _sync_client(tmp_path, mc, inst_store, inst_router)
    try:
        assert inst_store.list_providers() == []
        assert sync.poll_once() is True

        # The synced model resolves locally, with the real key decrypted from
        # the sealed blob and re-encrypted under the instance's own crypto.
        resolved = inst_store.resolve("demo-model")
        assert resolved is not None
        assert resolved.api_key == "gsk_SUPERSECRET_KEY"
        assert resolved.base_url == "https://api.groq.com/openai/v1"
        assert inst_store.list_providers()[0].origin_gateway == "manager-gw"

        # Second poll with no change is a no-op (no needless adapter churn).
        assert sync.poll_once() is False
    finally:
        sync.close()


def test_api_key_never_travels_in_plaintext(tmp_path):
    manager = _make_manager(tmp_path)
    mc = TestClient(manager)
    prov = mc.post("/v1/admin/providers", headers=_headers(), json={
        "name": "groq", "kind": "openai-compatible", "base_url": "https://x", "api_key": "gsk_PLAINTEXT_LEAK_CHECK",
    }).json()
    mc.post("/v1/admin/models", headers=_headers(),
            json={"model_id": "m1", "provider_id": prov["provider_id"]})

    # Call the sync endpoint directly and inspect the raw response body.
    priv, pub = generate_keypair()
    r = mc.post("/v1/admin/providers/sync", headers=_headers(), json={"gateway_id": "rahul", "pubkey": pub})
    assert r.status_code == 200
    raw = r.text
    assert "gsk_PLAINTEXT_LEAK_CHECK" not in raw  # the secret must not appear anywhere
    body = r.json()
    assert body["providers"][0]["sealed_api_key"]["ciphertext"]  # it's sealed instead
    assert body["providers"][0]["key_last4"] == "HECK"  # non-secret hint is fine


def test_live_apply_change_no_restart(tmp_path):
    manager = _make_manager(tmp_path)
    mc = TestClient(manager)
    prov = mc.post("/v1/admin/providers", headers=_headers(), json={
        "name": "groq", "kind": "openai-compatible", "base_url": "https://x", "api_key": "k1",
    }).json()
    mc.post("/v1/admin/models", headers=_headers(),
            json={"model_id": "demo", "provider_id": prov["provider_id"], "upstream_model": "u1"})

    inst_store = SqliteProviderStore(_crypto(), str(tmp_path / "inst.sqlite"))
    inst_router = DynamicProviderRouter(inst_store)
    sync = _sync_client(tmp_path, mc, inst_store, inst_router)
    try:
        sync.poll_once()
        assert inst_store.resolve("demo").upstream_model == "u1"

        # Manager adds a second model; instance sees it on the next poll (no restart).
        mc.post("/v1/admin/models", headers=_headers(),
                json={"model_id": "demo2", "provider_id": prov["provider_id"], "upstream_model": "u2"})
        assert sync.poll_once() is True
        assert inst_store.resolve("demo2") is not None
        assert inst_store.resolve("demo2").upstream_model == "u2"
    finally:
        sync.close()


def test_fail_open_manager_down_keeps_last_known_registry(tmp_path):
    manager = _make_manager(tmp_path)
    mc = TestClient(manager)
    prov = mc.post("/v1/admin/providers", headers=_headers(), json={
        "name": "groq", "kind": "openai-compatible", "base_url": "https://x", "api_key": "k1",
    }).json()
    mc.post("/v1/admin/models", headers=_headers(), json={"model_id": "demo", "provider_id": prov["provider_id"]})

    inst_store = SqliteProviderStore(_crypto(), str(tmp_path / "inst.sqlite"))
    inst_router = DynamicProviderRouter(inst_store)
    sync = _sync_client(tmp_path, mc, inst_store, inst_router)
    try:
        sync.poll_once()
        assert inst_store.resolve("demo") is not None

        # Now the manager is unreachable: poll must NOT wipe the registry.
        def _down(request):
            raise httpx.ConnectError("manager down")
        sync._client = httpx.Client(transport=httpx.MockTransport(_down))
        assert sync.poll_once() is False
        assert inst_store.resolve("demo") is not None  # last-known-good preserved
    finally:
        sync.close()


def test_sync_endpoint_requires_admin_and_pubkey(tmp_path):
    manager = _make_manager(tmp_path)
    mc = TestClient(manager)
    # no auth
    assert mc.post("/v1/admin/providers/sync", json={"pubkey": "ab"}).status_code == 401
    # missing pubkey
    assert mc.post("/v1/admin/providers/sync", headers=_headers(), json={}).status_code == 400
    # bad hex
    assert mc.post("/v1/admin/providers/sync", headers=_headers(), json={"pubkey": "zz"}).status_code == 400


def test_manager_exclusive_blocks_local_provider_add_on_instance(tmp_path):
    """On a syncing instance, local provider/model adds are refused (409)."""
    app = FastAPI()
    app.include_router(admin_api.router)

    class _Settings:
        admin_key = SHARED
        gateway_id = "rahul-gateway"

    app.state.settings = _Settings()
    app.state.provider_store = SqliteProviderStore(_crypto(), str(tmp_path / "inst.sqlite"))
    app.state.provider_sync = object()  # presence => syncing instance
    client = TestClient(app)

    r = client.post("/v1/admin/providers", headers=_headers(),
                    json={"name": "x", "kind": "ollama", "base_url": "http://x"})
    assert r.status_code == 409
    r = client.post("/v1/admin/models", headers=_headers(), json={"model_id": "m", "provider_id": "p"})
    assert r.status_code == 409
    assert json.loads(r.text)["detail"].startswith("providers/models are managed centrally")
