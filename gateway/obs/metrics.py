"""Prometheus metrics: request duration per stage, findings by label/action,
budget/rate-limit counters. A dedicated registry (not the global default)
so tests can instantiate fresh metrics per test without collisions.
"""
from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest

REGISTRY = CollectorRegistry()

REQUEST_DURATION_SECONDS = Histogram(
    "monoai_request_duration_seconds",
    "Request duration per pipeline stage",
    ["stage"],
    registry=REGISTRY,
)

FINDINGS_TOTAL = Counter(
    "monoai_findings_total",
    "Detected spans by label and policy action",
    ["label", "action"],
    registry=REGISTRY,
)

BUDGET_REJECTIONS_TOTAL = Counter(
    "monoai_budget_rejections_total",
    "Requests rejected for exceeding a key's monthly budget",
    registry=REGISTRY,
)

RATE_LIMIT_REJECTIONS_TOTAL = Counter(
    "monoai_rate_limit_rejections_total",
    "Requests rejected by the per-key rate limiter",
    registry=REGISTRY,
)

INJECTION_FLAGGED_TOTAL = Counter(
    "monoai_injection_flagged_total",
    "Messages flagged by the injection detector, by action taken",
    ["action"],
    registry=REGISTRY,
)

INJECTION_JUDGE_INVOCATIONS_TOTAL = Counter(
    "monoai_injection_judge_invocations_total",
    "Tier 2.5 semantic injection judge invocations, by backend and availability",
    ["backend", "available"],
    registry=REGISTRY,
)


def render() -> bytes:
    return generate_latest(REGISTRY)
