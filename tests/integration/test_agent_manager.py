"""End-to-end manager side of the manager/agent split: enroll -> sealed
ingest into the EXISTING hash-chained audit log -> policy pull -> heartbeat
drift. Builds a minimal app mounting only the agents router (same style as
tests/integration/test_auth.py) so no Valkey/full lifespan is needed."""
from __future__ import annotations

import json

from agents.store import SqliteAgentStore
from api import agents as agents_api
from audit.chain import AuditChain, verify
from audit.sinks import JsonlSink, read_jsonl
from contracts.agent import AgentEventPayload, SealedEnvelope
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nacl.public import PrivateKey
from policy.store import PolicyStore
from vault.box import generate_keypair, seal

ADMIN = "test-admin-key"


def _make_app(tmp_path):
    app = FastAPI()
    app.include_router(agents_api.router)

    class _Settings:
        admin_key = ADMIN
        agent_enroll_token_ttl_s = 3600.0

    audit_path = str(tmp_path / "audit.jsonl")
    app.state.settings = _Settings()
    app.state.agent_store = SqliteAgentStore(str(tmp_path / "agents.sqlite"))
    app.state.manager_agent_key = PrivateKey.generate()
    app.state.policy_store = PolicyStore()
    app.state.policy_store.load_dir("./policies")
    app.state.audit_chain = AuditChain(JsonlSink(audit_path))
    app.state._audit_path = audit_path
    return app


def _enroll(client, policy_id="default"):
    r = client.post("/v1/admin/agents/enroll-token", headers={"Authorization": f"Bearer {ADMIN}"})
    token = r.json()["token"]
    priv, pub = generate_keypair()
    r = client.post("/v1/agent/enroll", json={"token": token, "pubkey": pub, "hostname": "edge-1", "policy_id": policy_id})
    assert r.status_code == 200, r.text
    body = r.json()
    return priv, pub, body


def test_enroll_returns_agent_id_and_manager_pubkey(tmp_path):
    client = TestClient(_make_app(tmp_path))
    _, _, body = _enroll(client)
    assert body["agent_id"].startswith("agt_")
    assert len(bytes.fromhex(body["manager_pubkey"])) == 32


def test_enroll_token_gen_requires_admin(tmp_path):
    client = TestClient(_make_app(tmp_path))
    assert client.post("/v1/admin/agents/enroll-token").status_code == 401


def test_ingest_writes_into_existing_hash_chain(tmp_path):
    app = _make_app(tmp_path)
    client = TestClient(app)
    priv, _, body = _enroll(client)
    agent_id, manager_pub = body["agent_id"], body["manager_pubkey"]

    events = [
        AgentEventPayload(ts=1.0, request_id="r1", session_id="s1", event="completed",
                          policy_id="default", policy_version=body["policy_version"],
                          span_counts_by_label={"EMAIL": 1}, redacted_count=1).model_dump(),
        AgentEventPayload(ts=2.0, request_id="r2", session_id="s1", event="blocked",
                          policy_id="default", policy_version=body["policy_version"],
                          blocked_labels=["CREDIT_CARD"]).model_dump(),
    ]
    nonce, ct = seal(priv, manager_pub, json.dumps(events))
    envelope = SealedEnvelope(agent_id=agent_id, nonce=nonce, ciphertext=ct)
    r = client.post("/v1/agent/ingest", json=envelope.model_dump())
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] == 2

    # Records landed in the ONE existing chain, tagged with agent_id, and the
    # chain still verifies.
    records = read_jsonl(app.state._audit_path)
    assert len(records) == 2
    assert all(rec.agent_id == agent_id for rec in records)
    assert {rec.event for rec in records} == {"completed", "blocked"}
    assert verify(records)


def test_ingest_rejects_forged_sender(tmp_path):
    app = _make_app(tmp_path)
    client = TestClient(app)
    _, _, body = _enroll(client)
    agent_id, manager_pub = body["agent_id"], body["manager_pubkey"]

    # Seal with an attacker key that is NOT the enrolled agent's key.
    forged_priv, _ = generate_keypair()
    nonce, ct = seal(forged_priv, manager_pub, json.dumps([]))
    r = client.post("/v1/agent/ingest", json={"agent_id": agent_id, "nonce": nonce, "ciphertext": ct})
    assert r.status_code == 401


def test_ingest_refused_for_revoked_agent(tmp_path):
    app = _make_app(tmp_path)
    client = TestClient(app)
    priv, _, body = _enroll(client)
    agent_id, manager_pub = body["agent_id"], body["manager_pubkey"]
    app.state.agent_store.revoke(agent_id)
    nonce, ct = seal(priv, manager_pub, json.dumps([]))
    r = client.post("/v1/agent/ingest", json={"agent_id": agent_id, "nonce": nonce, "ciphertext": ct})
    assert r.status_code == 403


def test_policy_pull_returns_yaml_and_version(tmp_path):
    app = _make_app(tmp_path)
    client = TestClient(app)
    _, _, body = _enroll(client)
    r = client.get("/v1/agent/policy", params={"agent_id": body["agent_id"]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["version"] == body["policy_version"]
    assert "policy_yaml" in data and "policy_id" in data["policy_yaml"]


def test_heartbeat_reports_policy_drift(tmp_path):
    app = _make_app(tmp_path)
    client = TestClient(app)
    _, _, body = _enroll(client)
    # Agent claims a stale version -> manager flags drift.
    r = client.post("/v1/agent/heartbeat", json={"agent_id": body["agent_id"], "policy_version": "stale-vN"})
    assert r.status_code == 200, r.text
    hb = r.json()
    assert hb["policy_stale"] is True
    assert hb["status"] == "online"
    # Agent on the current version -> no drift.
    r = client.post("/v1/agent/heartbeat", json={"agent_id": body["agent_id"], "policy_version": body["policy_version"]})
    assert r.json()["policy_stale"] is False
