#!/usr/bin/env python3
"""Gateway per-stage + end-to-end latency percentiles, driven directly
through Orchestrator (no live HTTP server needed) with StubProvider so
this runs anywhere without external dependencies -- real network p50/p95
against a live server is a follow-up, not this pass (see DECISIONS.md).
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

from audit.chain import AuditChain
from audit.sinks import JsonlSink
from detect.pipeline import DetectionPipeline
from orchestrator import Orchestrator
from pii import PiiEngine
from policy.store import PolicyStore
from providers.fallback_chain import FallbackChain, Route
from providers.stub import StubProvider
from vault.crypto import VaultCrypto
from vault.storage.sqlite_store import SqliteVaultStore

REPO_ROOT = Path(__file__).resolve().parents[1]
N_REQUESTS = 50


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


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = min(len(values) - 1, int(len(values) * p))
    return values[idx]


async def run() -> dict:
    pipeline = DetectionPipeline(use_onnx_ner=False)
    crypto = VaultCrypto(_FakeRedis())
    vault = SqliteVaultStore(crypto, storage_path=str(REPO_ROOT / "bench" / ".bench_vault.sqlite"))
    pii = PiiEngine(pipeline, vault, "bench-secret")
    policy_store = PolicyStore()
    policy_store.load_dir(str(REPO_ROOT / "policies"))
    provider = StubProvider()
    routes_by_tier = {
        tier: [Route(provider=provider, model_id=tier, provider_name="bench")]
        for tier in ("simple", "moderate", "complex")
    }
    fallback_chain = FallbackChain(routes_by_tier, max_retries_per_route=0)
    audit_chain = AuditChain(JsonlSink(str(REPO_ROOT / "bench" / ".bench_audit.jsonl")))
    orch = Orchestrator(pii, policy_store, fallback_chain, audit_chain, {}, {})

    totals_ms = []
    for i in range(N_REQUESTS):
        t0 = time.perf_counter()
        await orch.chat({"messages": [{"role": "user", "content": f"email me at user{i}@example.com please"}]})
        totals_ms.append((time.perf_counter() - t0) * 1000.0)

    vault.close()
    return {
        "n": N_REQUESTS,
        "p50_ms": _percentile(totals_ms, 0.50),
        "p95_ms": _percentile(totals_ms, 0.95),
        "p99_ms": _percentile(totals_ms, 0.99),
    }


def render_markdown(results: dict) -> str:
    return (
        f"### Gateway end-to-end latency (StubProvider, n={results['n']} sequential requests)\n\n"
        "| Percentile | Latency |\n"
        "|---|---|\n"
        f"| p50 | {results['p50_ms']:.2f}ms |\n"
        f"| p95 | {results['p95_ms']:.2f}ms |\n"
        f"| p99 | {results['p99_ms']:.2f}ms |\n"
    )


if __name__ == "__main__":
    print(render_markdown(asyncio.run(run())))
