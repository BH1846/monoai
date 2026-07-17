"""Manager-side API for the Wazuh-style manager/agent split.

The manager is the existing gateway. These routes let a lightweight agent
running on ANOTHER host enroll once, then run semi-autonomously:

  POST /v1/admin/agents/enroll-token  (admin) mint a one-time enroll token
  GET  /v1/admin/agents               (admin) list agents + derived status
  DELETE /v1/admin/agents/{agent_id}  (admin) revoke an agent
  POST /v1/agent/enroll               token + agent pubkey -> agent_id + manager pubkey
  POST /v1/agent/ingest               sealed buffered events -> EXISTING hash-chained audit log
  GET  /v1/agent/policy?agent_id=X    current SENTINEL policy YAML + version (drift tracking)
  POST /v1/agent/heartbeat            liveness ping; tells the agent if its policy is stale

Admin routes reuse the existing MONOAI_ADMIN_KEY bearer (see api/admin.py);
no new auth style is introduced. Agent routes authenticate structurally:
/enroll by the one-time token, /ingest by a sealed envelope that only the
holder of the agent's private key could have produced.
"""
from __future__ import annotations

import json
from typing import Any

import yaml
from agents.store import EnrollmentError
from contracts.agent import (
    AgentEventPayload,
    EnrollRequest,
    EnrollResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    IngestResponse,
    SealedEnvelope,
)
from contracts.audit import AuditRecord
from fastapi import APIRouter, Header, HTTPException, Request
from nacl.exceptions import CryptoError
from vault.box import open_sealed

router = APIRouter()


def _check_admin(authorization: str | None, admin_key: str | None) -> None:
    if not admin_key:
        raise HTTPException(status_code=403, detail="admin endpoints disabled (MONOAI_ADMIN_KEY not set)")
    if authorization != f"Bearer {admin_key}":
        raise HTTPException(status_code=401, detail="missing or invalid admin key")


def _manager_pubkey_hex(request: Request) -> str:
    return request.app.state.manager_agent_key.public_key.encode().hex()


def _manager_privkey_hex(request: Request) -> str:
    return request.app.state.manager_agent_key.encode().hex()


# -- admin: enrollment authority ------------------------------------------


@router.post("/v1/admin/agents/enroll-token")
async def create_enroll_token(
    request: Request,
    body: dict[str, Any] | None = None,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    ttl_s = float((body or {}).get("ttl_s", request.app.state.settings.agent_enroll_token_ttl_s))
    raw_token, expires_at = request.app.state.agent_store.create_enrollment_token(ttl_s=ttl_s)
    return {"token": raw_token, "expires_at": expires_at}


@router.get("/v1/admin/agents")
async def list_agents(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    agents = request.app.state.agent_store.list_agents()
    latest = request.app.state.policy_store.latest_version
    out = []
    for a in agents:
        d = a.model_dump()
        try:
            d["policy_stale"] = a.policy_version != latest(a.policy_id)
        except KeyError:
            d["policy_stale"] = False
        out.append(d)
    return {"agents": out}


@router.delete("/v1/admin/agents/{agent_id}")
async def revoke_agent(
    agent_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    if request.app.state.agent_store.get(agent_id) is None:
        raise HTTPException(status_code=404, detail="unknown agent")
    request.app.state.agent_store.revoke(agent_id)
    return {"revoked": agent_id}


# -- agent: enroll --------------------------------------------------------


@router.post("/v1/agent/enroll", response_model=EnrollResponse)
async def enroll(request: Request, body: EnrollRequest) -> EnrollResponse:
    store = request.app.state.agent_store
    policy_store = request.app.state.policy_store
    try:
        policy_version = policy_store.latest_version(body.policy_id)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"unknown policy_id: {body.policy_id!r}")
    try:
        # Reject a malformed pubkey early with a clean 400 rather than a 500
        # deep inside agent_id derivation.
        bytes.fromhex(body.pubkey)
    except ValueError:
        raise HTTPException(status_code=400, detail="pubkey must be hex-encoded")
    try:
        agent = store.enroll(body.token, body.pubkey, body.hostname, body.policy_id, policy_version)
    except EnrollmentError as err:
        raise HTTPException(status_code=401, detail=str(err))
    return EnrollResponse(
        agent_id=agent.agent_id,
        manager_pubkey=_manager_pubkey_hex(request),
        policy_id=agent.policy_id,
        policy_version=policy_version,
    )


# -- agent: ingest buffered events into the existing audit chain ----------


@router.post("/v1/agent/ingest", response_model=IngestResponse)
async def ingest(request: Request, envelope: SealedEnvelope) -> IngestResponse:
    store = request.app.state.agent_store
    agent = store.get(envelope.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="unknown agent")
    if agent.status == "revoked":
        raise HTTPException(status_code=403, detail="agent revoked")

    # Authenticated open: this both decrypts AND proves the envelope was
    # sealed with the private key matching the agent's registered pubkey.
    try:
        plaintext = open_sealed(_manager_privkey_hex(request), agent.pubkey, envelope.nonce, envelope.ciphertext)
    except CryptoError:
        raise HTTPException(status_code=401, detail="envelope failed authentication")

    try:
        raw_events = json.loads(plaintext)
        events = [AgentEventPayload.model_validate(e) for e in raw_events]
    except Exception:
        raise HTTPException(status_code=400, detail="malformed ingest payload")

    audit_chain = request.app.state.audit_chain
    for ev in events:
        record = AuditRecord(
            ts=ev.ts,
            request_id=ev.request_id,
            session_id=ev.session_id,
            agent_id=agent.agent_id,
            event=ev.event,
            policy_id=ev.policy_id,
            policy_version=ev.policy_version,
            detector_versions=ev.detector_versions,
            pack_versions=ev.pack_versions,
            span_counts_by_label=ev.span_counts_by_label,
            blocked_labels=ev.blocked_labels,
            redacted_count=ev.redacted_count,
            pii_sanitize_ms=ev.pii_sanitize_ms,
        )
        audit_chain.append(record)

    store.touch_sync(agent.agent_id)
    return IngestResponse(accepted=len(events), last_hash=audit_chain.last_hash)


# -- agent: policy pull (drift detection) ---------------------------------


@router.get("/v1/agent/policy")
async def get_policy(request: Request, agent_id: str) -> dict[str, Any]:
    store = request.app.state.agent_store
    agent = store.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="unknown agent")
    if agent.status == "revoked":
        raise HTTPException(status_code=403, detail="agent revoked")

    policy_store = request.app.state.policy_store
    try:
        policy = policy_store.get(agent.policy_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown policy_id: {agent.policy_id!r}")

    # The manager's content-hash version is authoritative. We serialize the
    # policy body to YAML for the agent to cache + enforce locally, but the
    # agent keeps THIS version string (not a re-hash of its own
    # serialization) so drift comparison against the manager stays aligned.
    policy_yaml = yaml.safe_dump(policy.model_dump(mode="json", exclude={"version"}), sort_keys=False)
    store.set_policy_version(agent_id, policy.version)
    return {"policy_id": policy.policy_id, "version": policy.version, "policy_yaml": policy_yaml}


# -- agent: heartbeat -----------------------------------------------------


@router.post("/v1/agent/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(request: Request, body: HeartbeatRequest) -> HeartbeatResponse:
    store = request.app.state.agent_store
    agent = store.get(body.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="unknown agent")
    if agent.status == "revoked":
        raise HTTPException(status_code=403, detail="agent revoked")

    store.record_heartbeat(body.agent_id, body.policy_version, body.last_sync)
    try:
        latest = request.app.state.policy_store.latest_version(agent.policy_id)
    except KeyError:
        latest = body.policy_version
    return HeartbeatResponse(
        status="online",
        policy_version=latest,
        policy_stale=body.policy_version != latest,
    )
