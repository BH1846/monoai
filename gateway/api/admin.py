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


@router.post("/v1/admin/account")
async def save_admin_account(
    request: Request,
    body: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Associates the admin key that was just used to authenticate this
    call with `email`, so a future GET /v1/admin/account/{email} can hand
    it back without the console asking the admin to re-paste it."""
    admin_key = request.app.state.settings.admin_key
    _check_admin(authorization, admin_key)
    email = (body.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email is required")
    request.app.state.admin_account_store.save(email, admin_key)
    return {"email": email, "saved": True}


@router.get("/v1/admin/account/{email}")
async def get_admin_account(email: str, request: Request) -> dict[str, Any]:
    """Deliberately unauthenticated -- see gateway/auth/admin_account_store.py
    module docstring for the security tradeoff this accepts."""
    account = request.app.state.admin_account_store.get(email.strip().lower())
    if account is None:
        raise HTTPException(status_code=404, detail="no admin account saved for this email")
    return {"email": account.email, "admin_key": account.admin_key}


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


@router.get("/v1/admin/keys/{key_id}")
async def get_key(
    key_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    keys = [k for k in request.app.state.key_store.list_keys() if k.key_id == key_id]
    if not keys:
        raise HTTPException(status_code=404, detail="unknown key_id")
    return keys[0].model_dump(exclude={"key_hash"})


@router.post("/v1/admin/providers")
async def create_provider(
    request: Request,
    body: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    name = body.get("name")
    kind = body.get("kind")
    base_url = body.get("base_url")
    if not name or not kind or not base_url:
        raise HTTPException(status_code=400, detail="name, kind, and base_url are required")
    try:
        record = request.app.state.provider_store.add_provider(
            name=name, kind=kind, base_url=base_url, api_key=body.get("api_key"),
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return {
        "provider_id": record.provider_id, "name": record.name, "kind": record.kind,
        "base_url": record.base_url, "key_last4": record.key_last4, "enabled": record.enabled,
    }


@router.get("/v1/admin/providers")
async def list_providers(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    providers = request.app.state.provider_store.list_providers()
    return {
        "providers": [
            {
                "provider_id": p.provider_id, "name": p.name, "kind": p.kind, "base_url": p.base_url,
                "key_last4": p.key_last4, "enabled": p.enabled,
            }
            for p in providers
        ]
    }


@router.delete("/v1/admin/providers/{provider_id}")
async def delete_provider(
    provider_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    if not request.app.state.provider_store.delete_provider(provider_id):
        raise HTTPException(status_code=404, detail="unknown provider_id")
    return {"deleted": provider_id}


@router.post("/v1/admin/models")
async def create_model(
    request: Request,
    body: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    store = request.app.state.provider_store
    model_id = body.get("model_id")
    provider_id = body.get("provider_id")
    if not model_id or not provider_id:
        raise HTTPException(status_code=400, detail="model_id and provider_id are required")
    try:
        record = store.add_model(
            model_id=model_id, provider_id=provider_id,
            upstream_model=body.get("upstream_model"), display_name=body.get("display_name"),
        )
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return {
        "model_id": record.model_id, "provider_id": record.provider_id, "provider_name": record.provider_name,
        "upstream_model": record.upstream_model, "display_name": record.display_name, "enabled": record.enabled,
    }


@router.get("/v1/admin/models")
async def list_models(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    models = request.app.state.provider_store.list_models()
    return {
        "models": [
            {
                "model_id": m.model_id, "provider_id": m.provider_id, "provider_name": m.provider_name,
                "upstream_model": m.upstream_model, "display_name": m.display_name, "enabled": m.enabled,
            }
            for m in models
        ]
    }


@router.delete("/v1/admin/models/{model_id}")
async def delete_model(
    model_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    if not request.app.state.provider_store.delete_model(model_id):
        raise HTTPException(status_code=404, detail="unknown model_id")
    return {"deleted": model_id}


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
