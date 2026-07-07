"""G9: real OTLP export for both traces and metrics, wired by
OTEL_EXPORTER_OTLP_ENDPOINT -- degrades gracefully to console/stdout
exporters when it's absent (local dev, or a deployment that hasn't
stood up a collector yet), never fails app boot.

obs.tracing.py already owns the TracerProvider/`stage_span` machinery
used throughout the codebase (sanitize, detect, policy, vault,
provider routing, streaming rehydration, audit); `configure_otel()`
below is what actually points that machinery (and a companion
MeterProvider) at a real backend instead of tracing.py's in-memory
default. Call this once at gateway startup instead of the bare
`configure_tracing()` gateway/app.py used to call directly.

Metrics instruments tracked here (in addition to obs.metrics'
Prometheus counters/histograms, which stay for the /metrics endpoint):
  - request latency per pipeline stage (mirrors REQUEST_DURATION_SECONDS)
  - token consumption (prompt/completion, per request)
  - PII density (detected spans per 1000 characters of processed text)
  - rehydration overhead (ms spent resolving vaulted tokens back out)

All record_* helpers below are no-ops until configure_otel() has run
(e.g. under unit tests that never call it) -- callers never need to
check "is otel configured" themselves.
"""
from __future__ import annotations

from typing import Any, Optional

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import ConsoleSpanExporter

from obs.tracing import configure_tracing

_METER_NAME = "monoai.gateway"

_instruments: dict[str, Any] = {}


def configure_otel(
    otlp_endpoint: Optional[str] = None,
    service_name: str = "monoai-gateway",
) -> dict[str, Any]:
    """Configures the global TracerProvider (via
    obs.tracing.configure_tracing) and a global MeterProvider. Returns
    the exporters used so tests/callers can inspect what got wired up
    without hitting a real network.

    Real OTLP/HTTP export when `otlp_endpoint` is given; otherwise
    console exporters -- a missing/unreachable collector must never
    crash gateway startup (graceful degradation, per G9's spec)."""
    resource = Resource.create({"service.name": service_name})

    if otlp_endpoint:
        # Imported lazily: the otlp exporter package is an optional
        # extra in spirit (only exercised when an endpoint is actually
        # configured), and importing it eagerly would mean any
        # exporter-side issue affects deployments that never intended
        # to use it.
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        base = otlp_endpoint.rstrip("/")
        span_exporter: Any = OTLPSpanExporter(endpoint=f"{base}/v1/traces")
        metric_exporter: Any = OTLPMetricExporter(endpoint=f"{base}/v1/metrics")
    else:
        span_exporter = ConsoleSpanExporter()
        metric_exporter = ConsoleMetricExporter()

    configure_tracing(exporter=span_exporter, resource=resource)

    reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=15000)
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(meter_provider)

    meter = metrics.get_meter(_METER_NAME)
    _instruments["latency"] = meter.create_histogram(
        "monoai.request.latency", unit="ms", description="Request latency per pipeline stage"
    )
    _instruments["tokens"] = meter.create_counter(
        "monoai.tokens.consumed", unit="tokens", description="Token consumption by kind (prompt/completion)"
    )
    _instruments["pii_density"] = meter.create_histogram(
        "monoai.pii.density", unit="1", description="Detected PII spans per 1000 characters of processed text"
    )
    _instruments["rehydration_overhead"] = meter.create_histogram(
        "monoai.rehydration.overhead", unit="ms", description="Time spent rehydrating vaulted tokens back into output"
    )

    return {"span_exporter": span_exporter, "metric_exporter": metric_exporter}


def record_latency(stage: str, ms: float) -> None:
    inst = _instruments.get("latency")
    if inst is not None:
        inst.record(ms, {"stage": stage})


def record_tokens(count: int, kind: str) -> None:
    inst = _instruments.get("tokens")
    if inst is not None and count:
        inst.add(count, {"kind": kind})


def record_pii_density(spans_per_1k_chars: float) -> None:
    inst = _instruments.get("pii_density")
    if inst is not None:
        inst.record(spans_per_1k_chars)


def record_rehydration_overhead(ms: float) -> None:
    inst = _instruments.get("rehydration_overhead")
    if inst is not None:
        inst.record(ms)
