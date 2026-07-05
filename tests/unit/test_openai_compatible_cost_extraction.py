import httpx

from providers.openai_compatible import CloudRoute, OpenAICompatibleProvider
from router.contracts import Message, RequestContext


def _ctx(request_id: str) -> RequestContext:
    return RequestContext(request_id=request_id, messages=[Message(role="user", content="hi")], source_format="native")


async def test_cost_keyed_by_provider_request_id_not_orchestrator_uuid():
    """Regression test for a real bug found and fixed during this rewrite:
    cost must be retrievable by the SAME request_id the provider was
    called with, not some other id an orchestrator generates for itself."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "hello"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": 0.0042},
            },
        )

    provider = OpenAICompatibleProvider(
        base_url="https://example.test/v1",
        routes={"tier-model": CloudRoute(model="real-model", api_key="key")},
    )
    provider._clients["key"] = httpx.AsyncClient(
        base_url="https://example.test/v1", transport=httpx.MockTransport(handler)
    )

    response = await provider.complete("provider-request-id", "tier-model", _ctx("provider-request-id"))

    assert response.request_id == "provider-request-id"
    assert provider.pop_cost("provider-request-id") == 0.0042
    assert provider.pop_cost("some-other-orchestrator-uuid") is None
    # Popped once -- second pop for the same id returns None too.
    assert provider.pop_cost("provider-request-id") is None


async def test_no_cost_field_leaves_pop_cost_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "hello"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    provider = OpenAICompatibleProvider(
        base_url="https://example.test/v1",
        routes={"tier-model": CloudRoute(model="real-model", api_key="key")},
    )
    provider._clients["key"] = httpx.AsyncClient(
        base_url="https://example.test/v1", transport=httpx.MockTransport(handler)
    )

    await provider.complete("req-2", "tier-model", _ctx("req-2"))
    assert provider.pop_cost("req-2") is None
