"""Full manager/agent split, in-process: a real AgentRunner drives a real
manager app over httpx.ASGITransport. Proves the guarantees that matter:

  * enroll once, agent generates its OWN keypair (manager never sees privkey)
  * local SENTINEL Tier 0 detection runs on the agent and produces events
  * sealed sync lands events in the manager's EXISTING hash-chained audit log
  * when the manager is unreachable, events BUFFER and replay IN ORDER on
    reconnect -- nothing lost, nothing duplicated
"""
from __future__ import annotations

from agent_config import AgentSettings
from agents.store import SqliteAgentStore
from api import agents as agents_api
from audit.chain import AuditChain, verify
from audit.sinks import JsonlSink, read_jsonl
from client import ManagerClient, ManagerUnreachable
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nacl.public import PrivateKey
from policy.store import PolicyStore
from runner import AgentRunner

ADMIN = "test-admin-key"


def _make_manager(tmp_path) -> FastAPI:
    app = FastAPI()
    app.include_router(agents_api.router)

    class _Settings:
        admin_key = ADMIN
        agent_enroll_token_ttl_s = 3600.0

    app.state.settings = _Settings()
    app.state.agent_store = SqliteAgentStore(str(tmp_path / "agents.sqlite"))
    app.state.manager_agent_key = PrivateKey.generate()
    app.state.policy_store = PolicyStore()
    app.state.policy_store.load_dir("./policies")
    app.state._audit_path = str(tmp_path / "audit.jsonl")
    app.state.audit_chain = AuditChain(JsonlSink(app.state._audit_path))
    return app


def _manager_client(app) -> TestClient:
    # TestClient is itself a sync httpx.Client that bridges to the ASGI app,
    # so it doubles as the agent's injected ManagerClient transport AND the
    # admin caller that mints the enroll token.
    return TestClient(app)


def _mint_token(http: TestClient) -> str:
    r = http.post("/v1/admin/agents/enroll-token", headers={"Authorization": f"Bearer {ADMIN}"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _agent(tmp_path, http, token) -> AgentRunner:
    settings = AgentSettings(
        manager_url="", enroll_token=token, policy_id="default",
        hostname="edge-test", state_dir=str(tmp_path / "agent_state"),
        use_onnx_ner=False,  # Tier 0 regex is enough + deterministic for the test
    )
    return AgentRunner(settings, client=ManagerClient(client=http))


def test_enroll_and_online_sync(tmp_path):
    app = _make_manager(tmp_path)
    http = _manager_client(app)
    runner = _agent(tmp_path, http, _mint_token(http))
    try:
        runner.start()
        assert runner.identity.agent_id.startswith("agt_")
        # Manager stored only the PUBLIC key -- never the private key.
        stored = app.state.agent_store.get(runner.identity.agent_id)
        assert stored.pubkey == runner.identity.public_key
        assert runner.identity.private_key not in open(str(tmp_path / "agents.sqlite"), "rb").read().hex()

        assert runner.observe("please email me at jane@example.com", session_id="s0") is True
        acked = runner.sync_once()
        assert acked == 1

        records = read_jsonl(app.state._audit_path)
        assert len(records) == 1
        assert records[0].agent_id == runner.identity.agent_id
        assert records[0].span_counts_by_label.get("EMAIL") == 1
        assert verify(records)
    finally:
        runner.close()


def test_offline_buffering_then_ordered_replay(tmp_path):
    app = _make_manager(tmp_path)
    http = _manager_client(app)
    runner = _agent(tmp_path, http, _mint_token(http))
    try:
        runner.start()  # enroll + policy pull while online

        # --- go offline: swap in a client that always fails to reach the manager
        real_client = runner._client

        class _Down:
            def ingest(self, *a, **k):
                raise ManagerUnreachable("simulated outage")

            def close(self):
                pass

        runner._client = _Down()

        for i in range(3):
            assert runner.observe(f"contact user{i} at u{i}@example.com", session_id=f"s{i}") is True
        assert runner.sync_once() == 0  # manager down -> nothing acked
        assert runner._buffer.pending_count() == 3  # everything retained

        # --- reconnect: replay drains the buffer oldest-first
        runner._client = real_client
        acked = runner.sync_once()
        assert acked == 3
        assert runner._buffer.pending_count() == 0

        records = read_jsonl(app.state._audit_path)
        assert [r.session_id for r in records] == ["s0", "s1", "s2"]  # production order preserved
        assert verify(records)  # single chain still intact after replay
    finally:
        runner.close()


def test_policy_cached_locally_enables_offline_evaluation(tmp_path):
    app = _make_manager(tmp_path)
    http = _manager_client(app)
    runner = _agent(tmp_path, http, _mint_token(http))
    try:
        runner.start()
        assert runner._policy_cache.ready
        # Version the agent holds matches the manager's authoritative version.
        latest = app.state.policy_store.latest_version("default")
        assert runner._policy_cache.version == latest
        # observe() works with NO manager round-trip -- pure local enforcement.
        runner._client = None  # prove observe() never touches the manager
        assert runner.observe("email a@b.com", session_id="s0") is True
    finally:
        runner._buffer.close()
