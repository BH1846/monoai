"""Token-bucket rate limiter, per virtual key, backed by Valkey.

Phase 1 simplification (see DECISIONS.md): this reads then writes bucket
state as a single JSON blob via plain GET/SET, not a Lua EVAL script —
under truly concurrent bursts to the same key at the same instant there's
a small race window (two requests could both read the same pre-decrement
state). Correctness for the sequential/fake-clock proof tests this phase
ships is unaffected; a Lua-atomic version is a documented hardening item
for later.
"""
from __future__ import annotations

import json
import time


class TokenBucketRateLimiter:
    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    def allow(self, key_id: str, rate_rps: float, burst: float, now: float | None = None) -> tuple[bool, float]:
        now = now if now is not None else time.time()
        redis_key = f"ratelimit:{key_id}"

        raw = self._redis.get(redis_key)
        if raw is None:
            tokens = float(burst)
            last_refill = now
        else:
            state = json.loads(raw)
            tokens = state["tokens"]
            last_refill = state["last_refill"]

        elapsed = max(0.0, now - last_refill)
        tokens = min(float(burst), tokens + elapsed * rate_rps)

        allowed = tokens >= 1.0
        if allowed:
            tokens -= 1.0

        self._redis.set(redis_key, json.dumps({"tokens": tokens, "last_refill": now}).encode("utf-8"))
        return allowed, tokens
