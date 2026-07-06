"""G10 proof test: WebhookSink delivers records and fails open on
delivery errors (invariant #3: never affects the data path)."""
import httpx

from contracts.audit import AuditRecord
from audit.sinks import WebhookSink


def _record() -> AuditRecord:
    return AuditRecord(
        ts=1.0, request_id="r1", session_id="s1", event="completed",
        policy_id="default", policy_version="sha256:abc",
    )


def test_webhook_sink_posts_record():
    received = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(200)

    sink = WebhookSink("https://example.test/webhook")
    sink._client = httpx.Client(transport=httpx.MockTransport(handler))

    sink.write(_record())
    assert len(received) == 1


def test_webhook_sink_fails_open_on_delivery_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated network failure")

    sink = WebhookSink("https://example.test/webhook")
    sink._client = httpx.Client(transport=httpx.MockTransport(handler))

    sink.write(_record())  # must not raise
