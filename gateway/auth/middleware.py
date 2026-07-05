"""Auth checks (authenticate/budget/model-allowlist/rate-limit) as plain
functions, plus FastAPI exception-handler registration so any endpoint can
raise these errors and get the right HTTP status/body for free.
"""
from __future__ import annotations

import hashlib

from fastapi import FastAPI
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from auth.errors import AuthenticationError, BudgetExceededError, ModelNotAllowedError, RateLimitedError
from auth.models import VirtualKey
from auth.rate_limit import TokenBucketRateLimiter
from auth.store import KeyStore


def authenticate(authorization: str | None, key_store: KeyStore) -> VirtualKey:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError()
    raw_key = authorization[len("Bearer "):]
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    key = key_store.get_by_hash(key_hash)
    if key is None or not key.active:
        raise AuthenticationError()
    return key


def check_budget(key: VirtualKey) -> None:
    if key.budget_usd_monthly is not None and key.budget_usd_spent >= key.budget_usd_monthly:
        raise BudgetExceededError(key.key_id, key.budget_usd_monthly, key.budget_usd_spent)


def check_model_allowed(key: VirtualKey, model_id: str | None) -> None:
    if model_id is not None and key.model_allowlist is not None and model_id not in key.model_allowlist:
        raise ModelNotAllowedError(key.key_id, model_id, key.model_allowlist)


def check_rate_limit(key: VirtualKey, limiter: TokenBucketRateLimiter) -> None:
    allowed, tokens = limiter.allow(key.key_id, key.rate_limit_rps, key.rate_limit_burst)
    if not allowed:
        deficit = max(0.0, 1.0 - tokens)
        retry_after_ms = int((deficit / key.rate_limit_rps) * 1000) if key.rate_limit_rps > 0 else 1000
        raise RateLimitedError(key.rate_limit_rps, retry_after_ms)


def register_auth_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AuthenticationError)
    async def _auth_error(request: Request, exc: AuthenticationError) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"error": {"type": "authentication_error", "message": exc.message}},
        )

    @app.exception_handler(BudgetExceededError)
    async def _budget_error(request: Request, exc: BudgetExceededError) -> JSONResponse:
        return JSONResponse(
            status_code=402,
            content={
                "error": {
                    "type": "budget_exceeded",
                    "message": str(exc),
                    "key_id": exc.key_id,
                    "budget_usd_monthly": exc.budget_usd_monthly,
                    "budget_usd_spent": exc.budget_usd_spent,
                }
            },
        )

    @app.exception_handler(ModelNotAllowedError)
    async def _model_error(request: Request, exc: ModelNotAllowedError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "type": "model_not_allowed",
                    "message": str(exc),
                    "key_id": exc.key_id,
                    "allowed_models": exc.allowed_models,
                }
            },
        )

    @app.exception_handler(RateLimitedError)
    async def _rate_limit_error(request: Request, exc: RateLimitedError) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "type": "rate_limited",
                    "message": str(exc),
                    "retry_after_ms": exc.retry_after_ms,
                }
            },
            headers={"Retry-After": str(max(1, exc.retry_after_ms // 1000))},
        )
