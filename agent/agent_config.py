"""Agent config: env-driven, same setdefault-based .env loader pattern as
gateway/config.py, but a MUCH smaller surface -- an agent only needs to know
where the manager is, where to keep its own local state, and how often to
sync / poll / beat.

Crucially: there is NO Valkey config, NO vault master-key config, NO manager
DB path here. The agent runs on another host and holds only its own private
key + the manager's public key (see identity.py). Keeping those knobs out of
this file is the security boundary made concrete -- there is nothing to
misconfigure into sharing the manager's key material.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _load_dotenv(path: str | None = None) -> None:
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.isfile(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


@dataclass
class AgentSettings:
    # Where the manager (gateway) lives. On a real split this is the
    # manager's routable host, NOT localhost.
    manager_url: str = field(default_factory=lambda: os.environ.get("MANAGER_URL", "http://127.0.0.1:8000"))
    # One-time enrollment token from an admin (`POST /v1/admin/agents/enroll-token`).
    # Only consulted on first run; ignored once enrolled state exists.
    enroll_token: str | None = field(default_factory=lambda: os.environ.get("AGENT_ENROLL_TOKEN") or None)
    policy_id: str = field(default_factory=lambda: os.environ.get("AGENT_POLICY_ID", "default"))
    hostname: str = field(default_factory=lambda: os.environ.get("AGENT_HOSTNAME") or os.uname().nodename)

    # Local, agent-owned state dir: identity (keypair, agent_id, manager
    # pubkey), the offline buffer DB, and the cached policy all live here.
    state_dir: str = field(default_factory=lambda: os.environ.get("AGENT_STATE_DIR", "./agent_state"))

    # Detection: reuse core's ONNX NER (Tier 1) when available; regex/secrets
    # (Tier 0) always run. Same knob name as the gateway for consistency.
    use_onnx_ner: bool = field(default_factory=lambda: (os.environ.get("PII_USE_ONNX_NER", "true").lower() in ("1", "true", "yes", "on")))

    # Daemon loop intervals (seconds).
    sync_interval_s: float = field(default_factory=lambda: float(os.environ.get("AGENT_SYNC_INTERVAL_S", "10")))
    policy_poll_interval_s: float = field(default_factory=lambda: float(os.environ.get("AGENT_POLICY_POLL_INTERVAL_S", "60")))
    heartbeat_interval_s: float = field(default_factory=lambda: float(os.environ.get("AGENT_HEARTBEAT_INTERVAL_S", "30")))
    http_timeout_s: float = field(default_factory=lambda: float(os.environ.get("AGENT_HTTP_TIMEOUT_S", "10")))
    # Max events drained from the buffer per /ingest call (replay batching).
    ingest_batch_size: int = field(default_factory=lambda: int(os.environ.get("AGENT_INGEST_BATCH_SIZE", "200")))


def load_settings() -> AgentSettings:
    return AgentSettings()
