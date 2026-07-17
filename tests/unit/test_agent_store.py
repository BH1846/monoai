"""SqliteAgentStore: enrollment-token lifecycle + registry status derivation."""
from __future__ import annotations

import time

import pytest
from agents.store import EnrollmentError, SqliteAgentStore
from vault.box import generate_keypair


def _store(tmp_path, **kw) -> SqliteAgentStore:
    return SqliteAgentStore(str(tmp_path / "agents.sqlite"), **kw)


def test_enroll_consumes_token_and_registers_agent(tmp_path):
    store = _store(tmp_path)
    token, _ = store.create_enrollment_token()
    _, pub = generate_keypair()
    agent = store.enroll(token, pub, "host-a", "default", "v1")
    assert agent.agent_id.startswith("agt_")
    assert agent.pubkey == pub
    assert store.get(agent.agent_id) is not None


def test_enrollment_token_is_single_use(tmp_path):
    store = _store(tmp_path)
    token, _ = store.create_enrollment_token()
    _, pub1 = generate_keypair()
    _, pub2 = generate_keypair()
    store.enroll(token, pub1, "host-a", "default", "v1")
    with pytest.raises(EnrollmentError):
        store.enroll(token, pub2, "host-b", "default", "v1")


def test_unknown_and_expired_tokens_rejected(tmp_path):
    store = _store(tmp_path)
    _, pub = generate_keypair()
    with pytest.raises(EnrollmentError):
        store.enroll("et-nonexistent", pub, "host-a", "default", "v1")
    token, _ = store.create_enrollment_token(ttl_s=-1.0)  # already expired
    with pytest.raises(EnrollmentError):
        store.enroll(token, pub, "host-a", "default", "v1")


def test_status_derivation_online_then_offline(tmp_path):
    # 10ms window so the offline branch is exercised without a real sleep gap.
    store = _store(tmp_path, heartbeat_interval_s=0.005, missed_beats_offline=1)
    token, _ = store.create_enrollment_token()
    _, pub = generate_keypair()
    agent = store.enroll(token, pub, "host-a", "default", "v1")
    assert store.get(agent.agent_id).status == "enrolled"  # no heartbeat yet

    store.record_heartbeat(agent.agent_id, "v1", None)
    assert store.get(agent.agent_id).status == "online"

    time.sleep(0.02)  # exceed the 5ms freshness window
    assert store.get(agent.agent_id).status == "offline"


def test_revoke_is_terminal(tmp_path):
    store = _store(tmp_path)
    token, _ = store.create_enrollment_token()
    _, pub = generate_keypair()
    agent = store.enroll(token, pub, "host-a", "default", "v1")
    store.revoke(agent.agent_id)
    got = store.get(agent.agent_id)
    assert got.status == "revoked"
    # A heartbeat must not resurrect a revoked agent.
    store.record_heartbeat(agent.agent_id, "v1", None)
    assert store.get(agent.agent_id).status == "revoked"
