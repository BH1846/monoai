"""SqliteAgentStore: the manager's agent registry + one-time enrollment
tokens (manager/agent split).

Same construction shape as the other four gateway stores (auth/store.py,
auth/admin_account_store.py, auth/transaction_store.py,
providers/registry_store.py): a check_same_thread=False SQLite connection,
a CREATE TABLE IF NOT EXISTS schema, plain synchronous methods, a close().

Two tables:
  * enrollment_tokens -- one-time secrets minted by an admin. Only the
    SHA-256 hash is stored (same as virtual keys in auth/store.py); a token
    is single-use (consumed atomically) and expires.
  * agents -- one row per enrolled agent. Stores the agent's PUBLIC key
    only. The manager never sees an agent's private key; the security
    boundary is that the agent generates its keypair on its own host.

`status` is stored, but the authoritative online/offline flip is DERIVED on
read from `last_seen` vs the heartbeat freshness window (see
`_derive_status`), so a crashed agent that stops sending heartbeats reads as
offline without needing a background sweeper.
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time

from contracts.agent import AgentRecord, AgentStatus

_SCHEMA = """
CREATE TABLE IF NOT EXISTS enrollment_tokens (
    token_hash TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    used_at REAL,
    used_by_agent_id TEXT
);
CREATE TABLE IF NOT EXISTS agents (
    agent_id TEXT PRIMARY KEY,
    pubkey TEXT NOT NULL,
    hostname TEXT NOT NULL,
    status TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    last_seen REAL,
    last_sync REAL,
    enrolled_at REAL NOT NULL,
    revoked_at REAL
);
"""

_COLS = (
    "agent_id, pubkey, hostname, status, policy_id, policy_version, "
    "last_seen, last_sync, enrolled_at, revoked_at"
)


class EnrollmentError(Exception):
    """Raised when a one-time enrollment token is missing, expired, or
    already used. Surfaces as a 401 at the /enroll route."""


def _row_to_agent(row) -> AgentRecord:
    (agent_id, pubkey, hostname, status, policy_id, policy_version,
     last_seen, last_sync, enrolled_at, revoked_at) = row
    return AgentRecord(
        agent_id=agent_id, pubkey=pubkey, hostname=hostname, status=status,
        policy_id=policy_id, policy_version=policy_version,
        last_seen=last_seen, last_sync=last_sync,
        enrolled_at=enrolled_at, revoked_at=revoked_at,
    )


class SqliteAgentStore:
    def __init__(
        self,
        storage_path: str = "./gateway_agents.sqlite",
        heartbeat_interval_s: float = 30.0,
        missed_beats_offline: int = 3,
    ) -> None:
        self._conn = sqlite3.connect(storage_path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        # A live agent that has beaten within this window reads as "online";
        # past it, "offline". Matches the brief's "flip to offline after N
        # missed beats".
        self._offline_after_s = heartbeat_interval_s * missed_beats_offline

    # -- enrollment tokens (admin/CLI side) --------------------------------

    def create_enrollment_token(self, ttl_s: float = 3600.0) -> tuple[str, float]:
        """Mint a one-time token. Returns (raw_token, expires_at). Only the
        hash is persisted -- the raw token is shown to the admin once."""
        raw = "et-" + secrets.token_urlsafe(24)
        token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        now = time.time()
        expires_at = now + ttl_s
        self._conn.execute(
            "INSERT INTO enrollment_tokens (token_hash, created_at, expires_at, used_at, used_by_agent_id) "
            "VALUES (?, ?, ?, NULL, NULL)",
            (token_hash, now, expires_at),
        )
        self._conn.commit()
        return raw, expires_at

    def _consume_token(self, raw_token: str, agent_id: str) -> None:
        """Atomically validate + mark a token used. Raises EnrollmentError
        if unknown, expired, or already consumed. The UPDATE ... WHERE
        used_at IS NULL makes double-spend race-safe: a second concurrent
        enroll with the same token updates 0 rows."""
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        now = time.time()
        row = self._conn.execute(
            "SELECT expires_at, used_at FROM enrollment_tokens WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        if row is None:
            raise EnrollmentError("unknown enrollment token")
        expires_at, used_at = row
        if used_at is not None:
            raise EnrollmentError("enrollment token already used")
        if now > expires_at:
            raise EnrollmentError("enrollment token expired")
        updated = self._conn.execute(
            "UPDATE enrollment_tokens SET used_at = ?, used_by_agent_id = ? "
            "WHERE token_hash = ? AND used_at IS NULL",
            (now, agent_id, token_hash),
        ).rowcount
        if updated != 1:
            raise EnrollmentError("enrollment token already used")
        self._conn.commit()

    # -- agents ------------------------------------------------------------

    def enroll(self, raw_token: str, pubkey: str, hostname: str, policy_id: str, policy_version: str) -> AgentRecord:
        """Consume the token and register the agent. agent_id is derived
        from the agent's pubkey so it is stable and self-describing."""
        agent_id = "agt_" + hashlib.sha256(bytes.fromhex(pubkey)).hexdigest()[:16]
        self._consume_token(raw_token, agent_id)
        now = time.time()
        record = AgentRecord(
            agent_id=agent_id, pubkey=pubkey, hostname=hostname, status="enrolled",
            policy_id=policy_id, policy_version=policy_version, enrolled_at=now,
        )
        # INSERT OR REPLACE: re-enrolling the same host (same keypair) with a
        # fresh token is idempotent rather than a hard error.
        self._conn.execute(
            f"INSERT OR REPLACE INTO agents ({_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (record.agent_id, record.pubkey, record.hostname, record.status, record.policy_id,
             record.policy_version, record.last_seen, record.last_sync, record.enrolled_at, record.revoked_at),
        )
        self._conn.commit()
        return record

    def _derive_status(self, stored: AgentStatus, last_seen: float | None) -> AgentStatus:
        if stored == "revoked":
            return "revoked"
        if last_seen is None:
            return "enrolled"
        return "online" if (time.time() - last_seen) <= self._offline_after_s else "offline"

    def get(self, agent_id: str) -> AgentRecord | None:
        row = self._conn.execute(
            f"SELECT {_COLS} FROM agents WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        if row is None:
            return None
        agent = _row_to_agent(row)
        agent.status = self._derive_status(agent.status, agent.last_seen)
        return agent

    def list_agents(self) -> list[AgentRecord]:
        rows = self._conn.execute(f"SELECT {_COLS} FROM agents ORDER BY enrolled_at ASC").fetchall()
        agents = [_row_to_agent(r) for r in rows]
        for a in agents:
            a.status = self._derive_status(a.status, a.last_seen)
        return agents

    def record_heartbeat(self, agent_id: str, policy_version: str, last_sync: float | None) -> None:
        """Update last_seen (now) + the agent's reported policy_version and
        last_sync. Does not touch stored `status` -- that is derived on read."""
        now = time.time()
        self._conn.execute(
            "UPDATE agents SET last_seen = ?, policy_version = ?, last_sync = COALESCE(?, last_sync), "
            "status = 'online' WHERE agent_id = ? AND status != 'revoked'",
            (now, policy_version, last_sync, agent_id),
        )
        self._conn.commit()

    def set_policy_version(self, agent_id: str, policy_version: str) -> None:
        """Record the version handed to an agent on a /policy pull, for
        drift detection against the manager's latest."""
        self._conn.execute(
            "UPDATE agents SET policy_version = ? WHERE agent_id = ?",
            (policy_version, agent_id),
        )
        self._conn.commit()

    def touch_sync(self, agent_id: str) -> None:
        """Mark a successful /ingest: bump last_seen + last_sync to now."""
        now = time.time()
        self._conn.execute(
            "UPDATE agents SET last_seen = ?, last_sync = ? WHERE agent_id = ? AND status != 'revoked'",
            (now, now, agent_id),
        )
        self._conn.commit()

    def revoke(self, agent_id: str) -> None:
        self._conn.execute(
            "UPDATE agents SET status = 'revoked', revoked_at = ? WHERE agent_id = ?",
            (time.time(), agent_id),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
