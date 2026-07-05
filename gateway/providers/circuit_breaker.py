"""Per-route (provider, model_id) circuit breaker.

CLOSED: requests pass through; a `failure_threshold` run of consecutive
retryable failures opens the breaker.
OPEN: every request rejected immediately (no network call) until
`open_duration_s` elapses.
HALF_OPEN: exactly one probe request allowed through; success -> CLOSED,
failure -> back to OPEN with the timer reset.
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Callable


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        open_duration_s: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._open_duration_s = open_duration_s
        self._clock = clock
        self._consecutive_failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at: float | None = None
        self._probe_in_flight = False

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            if self._clock() - self._opened_at >= self._open_duration_s:
                return CircuitState.HALF_OPEN
        return self._state

    def allow_request(self) -> bool:
        current = self.state
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.HALF_OPEN:
            if self._probe_in_flight:
                return False
            self._probe_in_flight = True
            return True
        return False  # OPEN, not yet eligible to probe

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at = None
        self._probe_in_flight = False

    def record_failure(self) -> None:
        was_half_open = self.state == CircuitState.HALF_OPEN
        self._probe_in_flight = False
        if was_half_open:
            self._state = CircuitState.OPEN
            self._opened_at = self._clock()
            return
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = self._clock()
