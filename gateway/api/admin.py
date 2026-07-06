"""Admin CRUD: keys, policy reload, budgets. Gated behind a single
MONOAI_ADMIN_KEY bearer -- same single-shared-secret pattern used
elsewhere in this codebase (MONOAI_BEARER_TOKEN historically), scoped
only to admin operations, not the chat endpoint.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

router = APIRouter()


def _check_admin(authorization: str | None, admin_key: str | None) -> None:
    if not admin_key:
        raise HTTPException(status_code=403, detail="admin endpoints disabled (MONOAI_ADMIN_KEY not set)")
    if authorization != f"Bearer {admin_key}":
        raise HTTPException(status_code=401, detail="missing or invalid admin key")


@router.post("/v1/admin/keys")
async def create_key(
    request: Request,
    body: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    key_store = request.app.state.key_store
    raw_key, key = key_store.create_key(
        team_id=body.get("team_id"),
        policy_id=body.get("policy_id", "default"),
        model_allowlist=body.get("model_allowlist"),
        budget_usd_monthly=body.get("budget_usd_monthly"),
        rate_limit_rps=body.get("rate_limit_rps", 5.0),
        rate_limit_burst=body.get("rate_limit_burst", 20),
    )
    return {"key": raw_key, "key_id": key.key_id, "policy_id": key.policy_id, "team_id": key.team_id}


@router.get("/v1/admin/keys")
async def list_keys(
    request: Request,
    team_id: str | None = None,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    key_store = request.app.state.key_store
    keys = key_store.list_keys(team_id=team_id)
    return {"keys": [k.model_dump(exclude={"key_hash"}) for k in keys]}


@router.delete("/v1/admin/keys/{key_id}")
async def revoke_key(
    key_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    request.app.state.key_store.revoke(key_id)
    return {"revoked": key_id}


@router.post("/v1/admin/policies/reload")
async def reload_policies(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    policy_store = request.app.state.policy_store
    loaded = policy_store.load_dir(request.app.state.settings.policy_dir)
    return {"loaded": [{"policy_id": p.policy_id, "version": p.version} for p in loaded]}


@router.delete("/v1/admin/vault/{session_id}")
async def erase_session(
    session_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Right-to-erasure API (G11, DPDP/GDPR): permanently deletes every
    vaulted value for a session_id from whichever backend is configured
    (SQLite or Postgres)."""
    _check_admin(authorization, request.app.state.settings.admin_key)
    removed = request.app.state.vault_store.erase_session(session_id)
    return {"session_id": session_id, "erased_count": removed}


@router.post("/v1/admin/vault/sweep-expired")
async def sweep_expired_vault_entries(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """TTL sweeper (G11), triggerable on a schedule (cron/systemd timer)
    against a running gateway rather than needing its own process."""
    _check_admin(authorization, request.app.state.settings.admin_key)
    removed = request.app.state.vault_store.sweep_expired()
    return {"swept_count": removed}


@router.get("/v1/admin/budgets/{key_id}")
async def get_budget(
    key_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    key_store = request.app.state.key_store
    keys = [k for k in key_store.list_keys() if k.key_id == key_id]
    if not keys:
        raise HTTPException(status_code=404, detail="unknown key_id")
    key = keys[0]
    return {
        "key_id": key.key_id,
        "budget_usd_monthly": key.budget_usd_monthly,
        "budget_usd_spent": key.budget_usd_spent,
    }
