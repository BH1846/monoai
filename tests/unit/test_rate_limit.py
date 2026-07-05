from auth.rate_limit import TokenBucketRateLimiter


class _FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def get(self, key: str):
        return self._store.get(key)

    def set(self, key: str, value: bytes, nx: bool = False):
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True


def test_allows_up_to_burst_then_blocks():
    limiter = TokenBucketRateLimiter(_FakeRedis())
    now = 1000.0
    # burst=3: first 3 requests at the same instant succeed, 4th fails.
    results = [limiter.allow("key-a", rate_rps=1.0, burst=3, now=now)[0] for _ in range(4)]
    assert results == [True, True, True, False]


def test_token_bucket_refills_over_time():
    limiter = TokenBucketRateLimiter(_FakeRedis())
    now = 1000.0
    # Drain the bucket (burst=1).
    allowed, _ = limiter.allow("key-a", rate_rps=1.0, burst=1, now=now)
    assert allowed is True
    allowed, _ = limiter.allow("key-a", rate_rps=1.0, burst=1, now=now)
    assert allowed is False

    # 1 second later, at rate_rps=1.0, exactly one token has refilled.
    allowed, _ = limiter.allow("key-a", rate_rps=1.0, burst=1, now=now + 1.0)
    assert allowed is True


def test_separate_keys_have_independent_buckets():
    limiter = TokenBucketRateLimiter(_FakeRedis())
    now = 1000.0
    assert limiter.allow("key-a", rate_rps=1.0, burst=1, now=now)[0] is True
    assert limiter.allow("key-b", rate_rps=1.0, burst=1, now=now)[0] is True
