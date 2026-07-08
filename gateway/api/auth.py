"""Self-serve end-user accounts: POST /v1/auth/register creates a real
account *and* a virtual key in the same step, so a new user can start
calling /v1/chat/completions immediately -- no admin action required. The
admin still sees every one of these via GET /v1/admin/keys (team_id is set
to the owning email), same as any admin-created key.
"""
from __future__ import annotations

import re
from typing import Any

from auth.user_account_store import EmailAlreadyRegisteredError
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MIN_PASSWORD_LEN = 8


def _normalize_email(raw: str | None) -> str:
    email = (raw or "").strip().lower()
    if not email or not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="a valid email is required")
    return email


def _validate_password(raw: str | None) -> str:
    password = raw or ""
    if len(password) < _MIN_PASSWORD_LEN:
        raise HTTPException(status_code=400, detail=f"password must be at least {_MIN_PASSWORD_LEN} characters")
    return password


def _key_snapshot(request: Request, key_id: str, email: str) -> dict[str, Any]:
    """Live budget/active state for the key backing `email`, looked up by
    team_id (set to the email at registration) since KeyStore has no
    get-by-id. Falls back to key_id-only fields if the key was somehow
    deleted out from under the account."""
    for key in request.app.state.key_store.list_keys(team_id=email):
        if key.key_id == key_id:
            return {
                "policy_id": key.policy_id,
                "model_allowlist": key.model_allowlist,
                "budget_usd_monthly": key.budget_usd_monthly,
                "budget_usd_spent": key.budget_usd_spent,
                "active": key.active,
            }
    return {"policy_id": None, "model_allowlist": None, "budget_usd_monthly": None, "budget_usd_spent": None, "active": None}


@router.post("/v1/auth/register")
async def register(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    email = _normalize_email(body.get("email"))
    password = _validate_password(body.get("password"))

    user_account_store = request.app.state.user_account_store
    if user_account_store.exists(email):
        raise HTTPException(status_code=409, detail="an account already exists for this email")

    settings = request.app.state.settings
    key_store = request.app.state.key_store
    raw_key, key = key_store.create_key(
        team_id=email,
        policy_id="default",
        budget_usd_monthly=settings.self_serve_budget_usd_monthly,
    )
    try:
        account = user_account_store.register(email, password, key.key_id, raw_key)
    except EmailAlreadyRegisteredError:
        # Lost a race with a concurrent registration for the same email --
        # the just-created key is simply orphaned (harmless, admin can
        # revoke it from the Users tab) rather than left half-wired.
        key_store.revoke(key.key_id)
        raise HTTPException(status_code=409, detail="an account already exists for this email") from None

    return {
        "email": account.email,
        "key_id": account.key_id,
        "virtual_key": account.virtual_key,
        "team_id": key.team_id,
        **_key_snapshot(request, key.key_id, email),
    }


@router.post("/v1/auth/login")
async def login(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    email = _normalize_email(body.get("email"))
    password = body.get("password") or ""

    account = request.app.state.user_account_store.authenticate(email, password)
    if account is None:
        raise HTTPException(status_code=401, detail="invalid email or password")

    return {
        "email": account.email,
        "key_id": account.key_id,
        "virtual_key": account.virtual_key,
        **_key_snapshot(request, account.key_id, email),
    }
