"""First-run enrollment: generate-or-load the agent keypair, call the
manager's /enroll with the one-time token, and persist the returned agent_id
+ manager pubkey to local state.

Idempotent: if the agent is already enrolled (identity.json has agent_id +
manager_pubkey), this is a no-op and the existing identity is returned. So
the daemon can call `ensure_enrolled` on every startup without re-enrolling.
"""
from __future__ import annotations

import identity as identity_mod
from agent_config import AgentSettings
from client import ManagerClient
from identity import AgentIdentity


class EnrollmentRequired(Exception):
    """Raised when the agent is not yet enrolled and no enrollment token was
    provided to enroll with."""


def ensure_enrolled(settings: AgentSettings, client: ManagerClient) -> AgentIdentity:
    ident = identity_mod.load_or_create(settings.state_dir, settings.policy_id)
    if ident.enrolled:
        return ident

    if not settings.enroll_token:
        raise EnrollmentRequired(
            "agent is not enrolled and AGENT_ENROLL_TOKEN is not set -- mint one with "
            "`POST /v1/admin/agents/enroll-token` on the manager and set it in the agent env"
        )

    resp = client.enroll(settings.enroll_token, ident.public_key, settings.hostname, settings.policy_id)
    ident.agent_id = resp.agent_id
    ident.manager_pubkey = resp.manager_pubkey
    ident.policy_id = resp.policy_id
    identity_mod.save(settings.state_dir, ident)
    return ident
