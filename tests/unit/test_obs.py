"""G9 proof tests: OTel spans across all pipeline stages, Prometheus
/metrics endpoint, and a structural guarantee that no raw PII value ever
lands in a span attribute.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from audit.chain import AuditChain
from audit.sinks import JsonlSink
from detect.pipeline import DetectionPipeline
from obs.metrics import FINDINGS_TOTAL, REQUEST_DURATION_SECONDS, render
from obs.tracing import configure_tracing
from orchestrator import Orchestrator
from pii import PiiEngine
from policy.store import PolicyStore
from providers.fallback_chain import FallbackChain, Route
from providers.stub import StubProvider
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


def _build_orchestrator(tmp_path):
    pipeline = DetectionPipeline(use_onnx_ner=False)
    crypto = VaultCrypto(_FakeRedis())
    vault = SqliteVaultStore(crypto, storage_path=str(tmp_path / "vault.sqlite"))
    pii = PiiEngine(pipeline, vault, "test-server-secret")
    policy_store = PolicyStore()
    policy_store.load_dir("policies")
    provider = StubProvider()
    routes_by_tier = {
        tier: [Route(provider=provider, model_id=tier, provider_name="test")]
        for tier in ("simple", "moderate", "complex")
    }
    fallback_chain = FallbackChain(routes_by_tier, max_retries_per_route=0)
    audit_chain = AuditChain(JsonlSink(str(tmp_path / "audit.jsonl")))
    return Orchestrator(pii, policy_store, fallback_chain, audit_chain, {}, {})


async def test_trace_spans_cover_all_stages(tmp_path):
    exporter = InMemorySpanExporter()
    configure_tracing(exporter)
    orch = _build_orchestrator(tmp_path)

    # finance_strict keeps output_scan enabled (the default policy now has it
    # off), so the output_scan span is emitted for this coverage assertion.
    await orch.chat(
        {"messages": [{"role": "user", "content": "email me at a@b.com"}]},
        policy_id="finance_strict",
    )

    span_names = {s.name for s in exporter.get_finished_spans()}
    assert {"sanitize", "route", "provider", "output_scan", "rehydrate", "audit"} <= span_names


async def test_no_raw_values_in_spans(tmp_path):
    exporter = InMemorySpanExporter()
    configure_tracing(exporter)
    orch = _build_orchestrator(tmp_path)

    secret_email = "very-specific-address@example.com"
    await orch.chat({"messages": [{"role": "user", "content": f"email me at {secret_email}"}]})

    for span in exporter.get_finished_spans():
        for value in span.attributes.values():
            assert secret_email not in str(value)


def test_metrics_endpoint_exposes_request_histogram():
    REQUEST_DURATION_SECONDS.labels(stage="sanitize").observe(0.01)

    app = FastAPI()
    from api import metrics as metrics_api

    app.include_router(metrics_api.router)
    client = TestClient(app)

    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert b"monoai_request_duration_seconds" in resp.content


def test_metrics_render_includes_findings_counter():
    FINDINGS_TOTAL.labels(label="EMAIL", action="REVERSIBLE").inc()
    body = render()
    assert b"monoai_findings_total" in body
