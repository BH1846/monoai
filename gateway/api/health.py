from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health/live")
async def live() -> dict[str, Any]:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(request: Request) -> dict[str, Any]:
    checks: dict[str, bool] = {}

    valkey_client = getattr(request.app.state, "valkey_client", None)
    try:
        checks["valkey"] = bool(valkey_client is not None and valkey_client.ping())
    except Exception:
        checks["valkey"] = False

    policy_store = getattr(request.app.state, "policy_store", None)
    checks["policy_store"] = policy_store is not None and len(getattr(policy_store, "_policies", {})) > 0

    fallback_chain = getattr(request.app.state, "fallback_chain", None)
    checks["providers_configured"] = fallback_chain is not None and len(fallback_chain._routes_by_tier) > 0

    ok = all(checks.values())
    return {"status": "ok" if ok else "not_ready", "checks": checks}
