"""AgentRunner: the daemon that ties the pieces together.

Lifecycle:
  1. ensure_enrolled            (keypair, /enroll on first run)
  2. poll_policy_once           (pull + cache SENTINEL policy)
  3. loop, on independent intervals:
       - observe(text/files)    -> LocalSentinel Tier0/1 -> append to buffer
       - sync_once              -> drain buffer to /ingest IN ORDER
       - poll_policy_once       -> refresh cached policy (drift correction)
       - heartbeat_once         -> liveness + drift signal

The methods are split out (rather than buried in one loop) so they are
individually testable and so `run_forever` is a thin scheduler over them.
Every manager call is best-effort: ManagerUnreachable just means "stay
buffered, try next tick" -- that is the offline-tolerance guarantee.

`observe()` is the ingestion seam. A real deployment wires it to a local
traffic tap or file watcher; that host integration is out of scope this
pass, so the runner exposes the seam and the __main__ demo drives it
manually.
"""
from __future__ import annotations

import time

from agent_config import AgentSettings
from buffer import EventBuffer
from client import ManagerClient, ManagerRejected, ManagerUnreachable
from detect.pipeline import DetectionPipeline
from enroll import ensure_enrolled
from identity import AgentIdentity
from policy_cache import PolicyCache
from sentinel import LocalSentinel

# The agent runs the same detectors the gateway does; these version strings
# mirror gateway/app.py's DETECTOR_VERSIONS/PACK_VERSIONS so audit records
# ingested from an agent are attributable to the same detector revisions.
DETECTOR_VERSIONS = {"regex": "base_en-v1", "secrets": "base_en-v1", "ner": "base_en-v1", "locked_span": "base_en-v1"}
PACK_VERSIONS = {"base_en": "base_en-v1", "gulf_ar": "gulf_ar-v1"}


class AgentRunner:
    def __init__(self, settings: AgentSettings, client: ManagerClient | None = None) -> None:
        self._settings = settings
        self._client = client or ManagerClient(settings.manager_url, timeout_s=settings.http_timeout_s)
        self._identity: AgentIdentity | None = None
        self._buffer = EventBuffer(f"{settings.state_dir}/buffer.sqlite")
        self._policy_cache = PolicyCache(settings.state_dir)
        pipeline = DetectionPipeline(use_onnx_ner=settings.use_onnx_ner)
        self._sentinel = LocalSentinel(pipeline, DETECTOR_VERSIONS, PACK_VERSIONS)
        self._last_sync_ts: float | None = None

    @property
    def identity(self) -> AgentIdentity:
        assert self._identity is not None, "call start() before using the runner"
        return self._identity

    def start(self) -> None:
        """Enroll (idempotent) and prime the policy cache."""
        self._identity = ensure_enrolled(self._settings, self._client)
        # Best-effort first policy pull; if the manager is down we run on
        # whatever policy is already cached on disk (may be none until first
        # successful pull).
        try:
            self.poll_policy_once()
        except ManagerUnreachable:
            pass

    # -- ingestion seam ----------------------------------------------------

    def observe(self, text: str, session_id: str | None = None) -> bool:
        """Run local SENTINEL detection over one piece of local text and
        buffer the resulting event. Returns True if an event was buffered.
        No-op (returns False) if no policy is cached yet -- the agent won't
        fabricate decisions without a policy to apply."""
        policy = self._policy_cache.policy
        if policy is None:
            return False
        event = self._sentinel.scan_text(text, policy, self._policy_cache.version, session_id=session_id)
        self._buffer.append(event.model_dump_json(), event.ts)
        return True

    # -- manager sync ------------------------------------------------------

    def sync_once(self) -> int:
        """Drain the buffer to /ingest in order. Returns the number of events
        acked by the manager. Only deletes rows the manager confirmed, so a
        mid-flight failure never drops events -- they replay next tick."""
        if self._identity is None or not self._identity.enrolled:
            return 0
        total_acked = 0
        while True:
            batch = self._buffer.peek_batch(self._settings.ingest_batch_size)
            if not batch:
                break
            event_jsons = [b.payload_json for b in batch]
            try:
                resp = self._client.ingest(
                    self._identity.agent_id, self._identity.private_key,
                    self._identity.manager_pubkey, event_jsons,
                )
            except ManagerUnreachable:
                break  # stay buffered, retry next tick
            # Manager durably accepted this batch -> safe to delete.
            self._buffer.ack([b.seq for b in batch])
            total_acked += resp.accepted
            self._last_sync_ts = time.time()
            if len(batch) < self._settings.ingest_batch_size:
                break
        return total_acked

    def poll_policy_once(self) -> bool:
        """Pull the current policy from the manager and cache it. Returns
        True if the cached policy changed."""
        if self._identity is None or not self._identity.enrolled:
            return False
        data = self._client.get_policy(self._identity.agent_id)
        if data["version"] == self._policy_cache.version:
            return False
        self._policy_cache.update(data["policy_yaml"], data["version"])
        return True

    def heartbeat_once(self):
        """Send liveness + current policy version; returns the manager's
        HeartbeatResponse (or None if unreachable)."""
        if self._identity is None or not self._identity.enrolled:
            return None
        try:
            return self._client.heartbeat(self._identity.agent_id, self._policy_cache.version, self._last_sync_ts)
        except ManagerUnreachable:
            return None

    # -- scheduler ---------------------------------------------------------

    def run_forever(self, sleep=time.sleep) -> None:  # pragma: no cover - long-running loop
        self.start()
        next_sync = next_policy = next_beat = 0.0
        while True:
            now = time.monotonic()
            if now >= next_sync:
                self.sync_once()
                next_sync = now + self._settings.sync_interval_s
            if now >= next_policy:
                try:
                    if self.poll_policy_once():
                        pass
                except ManagerUnreachable:
                    pass
                except ManagerRejected:
                    pass
                next_policy = now + self._settings.policy_poll_interval_s
            if now >= next_beat:
                self.heartbeat_once()
                next_beat = now + self._settings.heartbeat_interval_s
            sleep(1.0)

    def close(self) -> None:
        self._buffer.close()
        self._client.close()
