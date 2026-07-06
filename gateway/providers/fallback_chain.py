"""Per-difficulty-tier ordered fallback chain: iterates routes in order,
skipping any whose circuit breaker is OPEN and not eligible to probe,
retrying within a route before moving to the next; a non-retryable
exception raises immediately (no point burning the rest of the chain on a
malformed request); if every route is exhausted, raises AllProvidersDownError.
"""
from __future__ import annotations

from dataclasses import dataclass

from router.contracts import ProviderResponse, RequestContext

from providers.base import ProviderAdapter
from providers.circuit_breaker import CircuitBreaker
from providers.retry import is_retryable, retry_with_backoff


@dataclass
class Route:
    provider: ProviderAdapter
    model_id: str
    provider_name: str


class AllProvidersDownError(Exception):
    def __init__(self, tier: str) -> None:
        super().__init__(f"all providers down for tier {tier!r}")
        self.tier = tier


@dataclass
class FallbackResult:
    response: ProviderResponse
    fallback_chain_position: int
    circuit_state: str
    route: Route


class FallbackChain:
    def __init__(
        self,
        routes_by_tier: dict[str, list[Route]],
        failure_threshold: int = 5,
        open_duration_s: float = 30.0,
        max_retries_per_route: int = 2,
    ) -> None:
        self._routes_by_tier = routes_by_tier
        self._failure_threshold = failure_threshold
        self._open_duration_s = open_duration_s
        self._max_retries_per_route = max_retries_per_route
        self._breakers: dict[tuple[str, str], CircuitBreaker] = {}

    def breaker_for(self, provider_name: str, model_id: str) -> CircuitBreaker:
        key = (provider_name, model_id)
        if key not in self._breakers:
            self._breakers[key] = CircuitBreaker(
                failure_threshold=self._failure_threshold, open_duration_s=self._open_duration_s
            )
        return self._breakers[key]

    async def dispatch(self, request_id: str, tier: str, ctx: RequestContext) -> FallbackResult:
        routes = self._routes_by_tier.get(tier, [])
        last_exc: Exception | None = None

        for position, route in enumerate(routes):
            breaker = self.breaker_for(route.provider_name, route.model_id)
            if not breaker.allow_request():
                continue

            async def _call(route=route):
                return await route.provider.complete(request_id, route.model_id, ctx)

            try:
                response = await retry_with_backoff(_call, max_retries=self._max_retries_per_route)
            except Exception as exc:
                last_exc = exc
                if not is_retryable(exc):
                    raise
                breaker.record_failure()
                continue

            breaker.record_success()
            return FallbackResult(
                response=response, fallback_chain_position=position, circuit_state=breaker.state.value, route=route
            )

        raise AllProvidersDownError(tier) from last_exc
