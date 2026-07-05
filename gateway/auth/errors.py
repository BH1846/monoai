from __future__ import annotations


class AuthenticationError(Exception):
    def __init__(self, message: str = "missing or invalid API key") -> None:
        super().__init__(message)
        self.message = message


class BudgetExceededError(Exception):
    def __init__(self, key_id: str, budget_usd_monthly: float, budget_usd_spent: float) -> None:
        super().__init__(f"monthly budget of ${budget_usd_monthly:.2f} exhausted")
        self.key_id = key_id
        self.budget_usd_monthly = budget_usd_monthly
        self.budget_usd_spent = budget_usd_spent


class ModelNotAllowedError(Exception):
    def __init__(self, key_id: str, model_id: str, allowed_models: list[str] | None) -> None:
        super().__init__(f"model {model_id!r} is not in this key's allowlist")
        self.key_id = key_id
        self.model_id = model_id
        self.allowed_models = allowed_models or []


class RateLimitedError(Exception):
    def __init__(self, rate_limit_rps: float, retry_after_ms: int) -> None:
        super().__init__(f"rate limit exceeded: {rate_limit_rps} req/s")
        self.rate_limit_rps = rate_limit_rps
        self.retry_after_ms = retry_after_ms
