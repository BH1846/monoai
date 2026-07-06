"""Adversarial property test: a BLOCK-classified raw value must never
appear in any client-visible or audited field, across many generated
prompts and both directions (input BLOCK -> request rejected; output
BLOCK -> model-leaked value redacted, not restored).
"""
from __future__ import annotations

import json
import random

import pytest

from audit.chain import AuditChain
from audit.sinks import JsonlSink
from detect.pipeline import DetectionPipeline
from orchestrator import BlockedContentError, Orchestrator
from pii import PiiEngine
from policy.store import PolicyStore
from providers.base import ProviderAdapter
from providers.fallback_chain import FallbackChain, Route
from router.contracts import ProviderResponse, RequestContext
from vault.crypto import VaultCrypto
from vault.storage.sqlite_store import SqliteVaultStore


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


def _luhn_valid_number(rng: random.Random) -> str:
    """Directly derives a check digit that satisfies the SAME algorithm as
    regex_stage._luhn_ok (parity computed over the FULL 16-digit string,
    not the 15-digit prefix) -- deriving the formula independently risks
    an off-by-one parity mismatch, as an earlier version of this helper
    had."""
    prefix = [rng.randint(0, 9) for _ in range(15)]
    for check_digit in range(10):
        candidate = prefix + [check_digit]
        total = 0
        parity = len(candidate) % 2
        for i, d in enumerate(candidate):
            if i % 2 == parity:
                d *= 2
                if d > 9:
                    d -= 9
            total += d
        if total % 10 == 0:
            return "".join(str(d) for d in candidate)
    raise AssertionError("no valid Luhn check digit found (should be impossible)")


def _random_ssn(rng: random.Random) -> str:
    return f"{rng.randint(100,999)}-{rng.randint(10,99)}-{rng.randint(1000,9999)}"


def _random_secret(rng: random.Random) -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "AKIA" + "".join(rng.choice(alphabet) for _ in range(16))


class _LeakingProvider(ProviderAdapter):
    """Simulates a model that leaks a BLOCK-classified value it was never given."""

    def __init__(self, leaked_value: str) -> None:
        self._leaked_value = leaked_value

    async def complete(self, request_id: str, model_id: str, ctx: RequestContext) -> ProviderResponse:
        return ProviderResponse(
            request_id=request_id, model_id=model_id, provider="leaky", content=f"Sure, here you go: {self._leaked_value}",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}, latency_ms=1.0,
        )


def _build_orchestrator(tmp_path, provider):
    pipeline = DetectionPipeline(use_onnx_ner=False)
    crypto = VaultCrypto(_FakeRedis())
    vault = SqliteVaultStore(crypto, storage_path=str(tmp_path / "vault.sqlite"))
    pii = PiiEngine(pipeline, vault, "test-server-secret")
    policy_store = PolicyStore()
    policy_store.load_dir("policies")
    routes_by_tier = {
        tier: [Route(provider=provider, model_id=tier, provider_name="test")]
        for tier in ("simple", "moderate", "complex")
    }
    fallback_chain = FallbackChain(routes_by_tier, max_retries_per_route=0)
    audit_chain = AuditChain(JsonlSink(str(tmp_path / "audit.jsonl")))
    return Orchestrator(pii, policy_store, fallback_chain, audit_chain, {}, {}), str(tmp_path / "audit.jsonl")


def _generated_block_values(seed: int, n: int) -> list[str]:
    rng = random.Random(seed)
    values = []
    for _ in range(n):
        kind = rng.choice(["ssn", "cc", "secret"])
        if kind == "ssn":
            values.append(_random_ssn(rng))
        elif kind == "cc":
            values.append(_luhn_valid_number(rng))
        else:
            values.append(_random_secret(rng))
    return values


@pytest.mark.parametrize("value", _generated_block_values(seed=42, n=12))
async def test_block_values_never_appear_in_any_output_field_input_side(tmp_path, value):
    orch, audit_path = _build_orchestrator(tmp_path, _LeakingProvider("unused"))
    payload = {"messages": [{"role": "user", "content": f"Here is the value: {value}, please help."}]}

    with pytest.raises(BlockedContentError) as excinfo:
        await orch.chat(payload)

    # Only labels, never the raw value, land in the audit record.
    dumped = json.dumps(excinfo.value.audit_record.model_dump(), default=str)
    assert value not in dumped


@pytest.mark.parametrize("value", _generated_block_values(seed=99, n=12))
async def test_block_values_never_appear_in_any_output_field_output_side(tmp_path, value):
    orch, audit_path = _build_orchestrator(tmp_path, _LeakingProvider(value))

    result = await orch.chat({"messages": [{"role": "user", "content": "tell me something"}]})

    assert value not in result.content
    with open(audit_path) as f:
        for line in f:
            assert value not in line
