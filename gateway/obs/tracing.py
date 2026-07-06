"""OpenTelemetry tracing: spans over auth, sanitize, route, provider
(attempt=n), stream_rehydrate, output_scan, audit.

No raw values in any span attribute -- only ids, counts, labels, timings
(unit-tested in tests/unit/test_obs.py).
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

_TRACER_NAME = "monoai.gateway"


def configure_tracing(exporter=None) -> Any:
    """Configures the global TracerProvider once. Returns the exporter
    (InMemorySpanExporter in tests, otherwise whatever was passed) so
    callers/tests can inspect finished spans."""
    provider = TracerProvider(resource=Resource.create({"service.name": "monoai-gateway"}))
    exporter = exporter if exporter is not None else InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return exporter


def get_tracer():
    return trace.get_tracer(_TRACER_NAME)


@contextmanager
def stage_span(stage: str, **attributes: Any) -> Iterator[None]:
    """attributes must only ever be safe metadata (ids/counts/labels) --
    never raw span text/values. Caller's responsibility; see
    test_obs.py::test_no_raw_values_in_spans for the enforcement test."""
    tracer = get_tracer()
    with tracer.start_as_current_span(stage) as span:
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(key, value)
        yield
