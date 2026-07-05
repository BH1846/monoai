from providers.circuit_breaker import CircuitBreaker, CircuitState


class _FakeClock:
    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def test_closed_by_default():
    cb = CircuitBreaker()
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


def test_opens_after_failure_threshold():
    clock = _FakeClock()
    cb = CircuitBreaker(failure_threshold=3, open_duration_s=10, clock=clock)
    for _ in range(3):
        assert cb.allow_request() is True
        cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False


def test_half_open_after_duration_elapses():
    clock = _FakeClock()
    cb = CircuitBreaker(failure_threshold=1, open_duration_s=10, clock=clock)
    cb.allow_request()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    clock.t = 10.0
    assert cb.state == CircuitState.HALF_OPEN


def test_half_open_single_probe_only():
    clock = _FakeClock()
    cb = CircuitBreaker(failure_threshold=1, open_duration_s=10, clock=clock)
    cb.allow_request()
    cb.record_failure()
    clock.t = 10.0
    assert cb.allow_request() is True  # the one probe
    assert cb.allow_request() is False  # a concurrent second request is denied


def test_successful_probe_closes_breaker():
    clock = _FakeClock()
    cb = CircuitBreaker(failure_threshold=1, open_duration_s=10, clock=clock)
    cb.allow_request()
    cb.record_failure()
    clock.t = 10.0
    assert cb.allow_request() is True
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


def test_failed_probe_reopens_breaker():
    clock = _FakeClock()
    cb = CircuitBreaker(failure_threshold=1, open_duration_s=10, clock=clock)
    cb.allow_request()
    cb.record_failure()
    clock.t = 10.0
    assert cb.allow_request() is True
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
