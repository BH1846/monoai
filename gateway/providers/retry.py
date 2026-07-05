"""Retry with full-jitter exponential backoff, within a single route
(before falling back to the next route in the chain)."""
from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Callable, TypeVar

import httpx

T = TypeVar("T")

# Explicit request-shape errors are never retryable (retrying elsewhere
# won't fix a malformed request). Everything else -- 429/5xx, timeouts,
# connection errors, and generic provider exceptions like StubProviderError
# -- is treated as a transient provider-health signal.
_NON_RETRYABLE_HTTP_STATUS = {400, 401, 403, 404, 422}


def is_retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code not in _NON_RETRYABLE_HTTP_STATUS
    return True


async def retry_with_backoff(
    fn: Callable[[], Awaitable[T]],
    max_retries: int = 2,
    base_delay_ms: float = 200.0,
    max_delay_ms: float = 2000.0,
) -> T:
    attempt = 0
    while True:
        try:
            return await fn()
        except Exception as exc:
            if not is_retryable(exc) or attempt >= max_retries:
                raise
            delay_ms = random.uniform(0, min(max_delay_ms, base_delay_ms * (2 ** attempt)))
            await asyncio.sleep(delay_ms / 1000.0)
            attempt += 1
