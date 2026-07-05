"""G2 proof tests: per-key virtual keys, budgets, rate limits, model
allowlists (replaces the old single-shared-bearer-token auth). This uses a
small standalone FastAPI test app wiring gateway/auth's real
authenticate/check_budget/check_model_allowed/check_rate_limit functions
around a dummy endpoint -- Step 9 wires the same functions into the real
/v1/chat/completions endpoint.
"""
from fastapi import FastAPI, Header, Request
from fastapi.testclient import TestClient

from auth.middleware import (
    authenticate,
    check_budget,
    check_model_allowed,
    check_rate_limit,
    register_auth_exception_handlers,
)
from auth.rate_limit import TokenBucketRateLimiter
from auth.store import SqliteKeyStore


class _FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def get(self, key: str):
        return self._store.get(key)

    def set(self, key: str, value: bytes, nx: bool = False):
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True


def _make_app(key_store: SqliteKeyStore, limiter: TokenBucketRateLimiter) -> FastAPI:
    app = FastAPI()
    register_auth_exception_handlers(app)

    @app.post("/v1/echo")
    async def echo(request: Request, authorization: str | None = Header(default=None)):
        body = await request.json()
        model_id = body.get("model")
        key = authenticate(authorization, key_store)
        check_budget(key)
        check_model_allowed(key, model_id)
        check_rate_limit(key, limiter)
        return {"ok": True, "key_id": key.key_id}

    return app


def test_key_isolation(tmp_path):
    store = SqliteKeyStore(str(tmp_path / "keys.sqlite"))
    limiter = TokenBucketRateLimiter(_FakeRedis())
    raw_a, key_a = store.create_key(team_id="team-a")
    raw_b, key_b = store.create_key(team_id="team-b")

    client = TestClient(_make_app(store, limiter))
    resp_a = client.post("/v1/echo", json={}, headers={"Authorization": f"Bearer {raw_a}"})
    resp_b = client.post("/v1/echo", json={}, headers={"Authorization": f"Bearer {raw_b}"})

    assert resp_a.status_code == 200
    assert resp_b.status_code == 200
    assert resp_a.json()["key_id"] == key_a.key_id
    assert resp_b.json()["key_id"] == key_b.key_id
    assert resp_a.json()["key_id"] != resp_b.json()["key_id"]

    resp_bad = client.post("/v1/echo", json={}, headers={"Authorization": "Bearer mk-nonexistent"})
    assert resp_bad.status_code == 401
    assert resp_bad.json()["error"]["type"] == "authentication_error"


def test_budget_exhaustion_returns_402(tmp_path):
    store = SqliteKeyStore(str(tmp_path / "keys.sqlite"))
    limiter = TokenBucketRateLimiter(_FakeRedis())
    raw, key = store.create_key(budget_usd_monthly=1.0)
    store.update_budget_spent(key.key_id, 1.0)

    client = TestClient(_make_app(store, limiter))
    resp = client.post("/v1/echo", json={}, headers={"Authorization": f"Bearer {raw}"})
    assert resp.status_code == 402
    assert resp.json()["error"]["type"] == "budget_exceeded"
    assert resp.json()["error"]["key_id"] == key.key_id


def test_rate_limit_429(tmp_path):
    store = SqliteKeyStore(str(tmp_path / "keys.sqlite"))
    limiter = TokenBucketRateLimiter(_FakeRedis())
    raw, key = store.create_key(rate_limit_rps=1.0, rate_limit_burst=1)

    client = TestClient(_make_app(store, limiter))
    resp1 = client.post("/v1/echo", json={}, headers={"Authorization": f"Bearer {raw}"})
    resp2 = client.post("/v1/echo", json={}, headers={"Authorization": f"Bearer {raw}"})

    assert resp1.status_code == 200
    assert resp2.status_code == 429
    assert "Retry-After" in resp2.headers


def test_model_allowlist_enforced(tmp_path):
    store = SqliteKeyStore(str(tmp_path / "keys.sqlite"))
    limiter = TokenBucketRateLimiter(_FakeRedis())
    raw, key = store.create_key(model_allowlist=["allowed-model"])

    client = TestClient(_make_app(store, limiter))
    resp_ok = client.post(
        "/v1/echo", json={"model": "allowed-model"}, headers={"Authorization": f"Bearer {raw}"}
    )
    resp_blocked = client.post(
        "/v1/echo", json={"model": "other-model"}, headers={"Authorization": f"Bearer {raw}"}
    )

    assert resp_ok.status_code == 200
    assert resp_blocked.status_code == 403
    assert resp_blocked.json()["error"]["type"] == "model_not_allowed"
