"""G6 proof tests: per-tier fallback chains, retry, circuit breaker."""
import pytest

from providers.fallback_chain import AllProvidersDownError, FallbackChain, Route
from providers.stub import StubProvider
from router.contracts import Message, RequestContext


def _ctx() -> RequestContext:
    return RequestContext(messages=[Message(role="user", content="hi")], source_format="native")


async def test_primary_429_falls_to_secondary():
    primary = StubProvider(provider_name="primary", models_always_fail={"primary-model"})
    secondary = StubProvider(provider_name="secondary")
    chain = FallbackChain(
        {
            "simple": [
                Route(provider=primary, model_id="primary-model", provider_name="primary"),
                Route(provider=secondary, model_id="secondary-model", provider_name="secondary"),
            ]
        },
        max_retries_per_route=0,
    )

    result = await chain.dispatch("req1", "simple", _ctx())
    assert result.response.provider == "secondary"
    assert result.fallback_chain_position == 1


async def test_all_down_returns_503_with_audit():
    # HTTP 503 + audit-record mapping happens in Step 9's API layer, which
    # catches this exact exception type -- this proves the underlying
    # signal it depends on.
    down_a = StubProvider(provider_name="a", models_always_fail={"model-a"})
    down_b = StubProvider(provider_name="b", models_always_fail={"model-b"})
    chain = FallbackChain(
        {
            "simple": [
                Route(provider=down_a, model_id="model-a", provider_name="a"),
                Route(provider=down_b, model_id="model-b", provider_name="b"),
            ]
        },
        max_retries_per_route=0,
    )

    with pytest.raises(AllProvidersDownError):
        await chain.dispatch("req1", "simple", _ctx())


async def test_circuit_opens_after_n_failures():
    down = StubProvider(provider_name="down", models_always_fail={"model-x"})
    chain = FallbackChain(
        {"simple": [Route(provider=down, model_id="model-x", provider_name="down")]},
        failure_threshold=3,
        max_retries_per_route=0,
    )

    call_count = 0
    original_complete = down.complete

    async def counting_complete(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return await original_complete(*args, **kwargs)

    down.complete = counting_complete

    for _ in range(3):
        with pytest.raises(AllProvidersDownError):
            await chain.dispatch("req1", "simple", _ctx())
    assert call_count == 3

    # Breaker is now open -- a 4th dispatch must NOT call the provider again.
    with pytest.raises(AllProvidersDownError):
        await chain.dispatch("req1", "simple", _ctx())
    assert call_count == 3
