"""ManagerClient: the agent's outbound HTTP link to the manager.

All /ingest traffic is sealed with an authenticated PyNaCl Box (agent
privkey + manager pubkey) via core/vault/box -- the manager verifies the
sender against the agent's registered pubkey. /enroll, /policy, /heartbeat
are plain JSON (enroll is authenticated by the one-time token; policy/
heartbeat by agent_id, which is not a secret -- the sensitive, forgeable
surface is /ingest, which is the one that is sealed).

Every call is best-effort from the daemon's perspective: network errors
raise ManagerUnreachable, which the runner treats as "stay buffered, retry
later" rather than a fatal error. That is the whole point of the split.
"""
from __future__ import annotations

import httpx
from contracts.agent import (
    EnrollResponse,
    HeartbeatResponse,
    IngestResponse,
    SealedEnvelope,
)
from vault.box import seal


class ManagerUnreachable(Exception):
    """Network-level failure talking to the manager. Non-fatal: the agent
    keeps buffering and retries on the next loop tick."""


class ManagerRejected(Exception):
    """The manager answered but refused the request (4xx/5xx). Carries the
    status so the runner can distinguish e.g. 403 revoked (terminal) from a
    transient 5xx."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"manager returned {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class ManagerClient:
    def __init__(self, manager_url: str = "", timeout_s: float = 10.0, client: httpx.Client | None = None) -> None:
        # `client` is injectable so tests can drive the manager in-process via
        # httpx.ASGITransport; production passes only manager_url.
        self._base = manager_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout_s)

    def _post(self, path: str, payload: dict) -> dict:
        try:
            resp = self._client.post(self._base + path, json=payload)
        except httpx.HTTPError as err:
            raise ManagerUnreachable(str(err)) from err
        if resp.status_code >= 400:
            detail = resp.json().get("detail", resp.text) if resp.headers.get("content-type", "").startswith("application/json") else resp.text
            raise ManagerRejected(resp.status_code, detail)
        return resp.json()

    def _get(self, path: str, params: dict) -> dict:
        try:
            resp = self._client.get(self._base + path, params=params)
        except httpx.HTTPError as err:
            raise ManagerUnreachable(str(err)) from err
        if resp.status_code >= 400:
            detail = resp.json().get("detail", resp.text) if resp.headers.get("content-type", "").startswith("application/json") else resp.text
            raise ManagerRejected(resp.status_code, detail)
        return resp.json()

    def enroll(self, token: str, pubkey: str, hostname: str, policy_id: str) -> EnrollResponse:
        return EnrollResponse.model_validate(
            self._post("/v1/agent/enroll", {"token": token, "pubkey": pubkey, "hostname": hostname, "policy_id": policy_id})
        )

    def ingest(self, agent_id: str, agent_privkey: str, manager_pubkey: str, event_jsons: list[str]) -> IngestResponse:
        """Seal a batch of already-serialized events and POST to /ingest.
        `event_jsons` are individual AgentEventPayload JSON strings; they are
        wrapped into a JSON array, sealed, and framed as a SealedEnvelope."""
        inner = "[" + ",".join(event_jsons) + "]"
        nonce, ciphertext = seal(agent_privkey, manager_pubkey, inner)
        envelope = SealedEnvelope(agent_id=agent_id, nonce=nonce, ciphertext=ciphertext)
        return IngestResponse.model_validate(self._post("/v1/agent/ingest", envelope.model_dump()))

    def get_policy(self, agent_id: str) -> dict:
        return self._get("/v1/agent/policy", {"agent_id": agent_id})

    def heartbeat(self, agent_id: str, policy_version: str, last_sync: float | None) -> HeartbeatResponse:
        return HeartbeatResponse.model_validate(
            self._post("/v1/agent/heartbeat", {"agent_id": agent_id, "policy_version": policy_version, "last_sync": last_sync})
        )

    def close(self) -> None:
        self._client.close()
