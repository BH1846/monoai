"""End-to-end tests: real pii_pipeline.Pipeline (Valkey required, see repo
root README) + monoai_router.lite.LiteRouter driven by StubProvider.

Requires a reachable Valkey/Redis instance -- see SENTINEL-2.0/.env or the
VALKEY_* environment variables. `docker compose up -d` (repo root) starts
one on 127.0.0.1:6380, matching SENTINEL-2.0/.env's defaults.
"""
from __future__ import annotations

import json
import os
import re
import tempfile

import pytest

from monoai_gateway.audit import AuditLogger
from monoai_gateway.orchestrator import BlockedContentError, Orchestrator
from monoai_gateway.pii import PiiGuard
from monoai_router.contracts import ProviderResponse, RequestContext
from monoai_router.lite.router import LiteRouter
from monoai_router.providers.base import ProviderAdapter
from monoai_router.providers.stub import StubProvider


class EchoingStubProvider(ProviderAdapter):
    """Echoes the full prompt text back verbatim (preserving PII_TOKEN
    placeholders), the way a well-behaved instruction-following LLM would.
    Records every ctx it was called with, so tests can assert the provider
    never received raw PII."""

    def __init__(self):
        self.seen_contexts: list[RequestContext] = []

    async def complete(self, request_id: str, model_id: str, ctx: RequestContext) -> ProviderResponse:
        self.seen_contexts.append(ctx)
        last = ctx.messages[-1]
        text = last.content if isinstance(last.content, str) else ""
        return ProviderResponse(
            request_id=request_id,
            model_id=model_id,
            provider="echo-stub",
            content=text,
            usage={"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            latency_ms=1.0,
        )


class DuplicatingStubProvider(ProviderAdapter):
    """Repeats every PII_TOKEN placeholder in the prompt twice in its reply
    -- simulates a real model referring to the same entity more than once
    (e.g. "hi NAME, ... take care, NAME")."""

    async def complete(self, request_id: str, model_id: str, ctx: RequestContext) -> ProviderResponse:
        last = ctx.messages[-1]
        text = last.content if isinstance(last.content, str) else ""
        tokens = re.findall(r"\[PII_TOKEN_\d{4,}\]", text)
        token = tokens[0] if tokens else "[missing]"
        return ProviderResponse(
            request_id=request_id,
            model_id=model_id,
            provider="dup-stub",
            content=f"Hi {token}, hope that helps! Take care, {token}.",
            usage={"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            latency_ms=1.0,
        )


@pytest.fixture
def tmp_paths(tmp_path):
    return {
        "vault": str(tmp_path / "vault.sqlite"),
        "router_log": str(tmp_path / "router.jsonl"),
        "audit_log": str(tmp_path / "audit.jsonl"),
    }


@pytest.fixture
async def orchestrator_with_echo(tmp_paths):
    guard = PiiGuard(vault_storage_path=tmp_paths["vault"])
    provider = EchoingStubProvider()
    router = LiteRouter(provider, log_path=tmp_paths["router_log"])
    audit = AuditLogger(path=tmp_paths["audit_log"])
    orch = Orchestrator(guard, router, audit)
    yield orch, provider, audit, tmp_paths
    await guard.close()


@pytest.fixture
async def orchestrator_with_stub(tmp_paths):
    guard = PiiGuard(vault_storage_path=tmp_paths["vault"])
    router = LiteRouter(StubProvider(), log_path=tmp_paths["router_log"])
    audit = AuditLogger(path=tmp_paths["audit_log"])
    orch = Orchestrator(guard, router, audit)
    yield orch, audit, tmp_paths
    await guard.close()


async def test_pii_round_trip_and_provider_never_sees_raw_pii(orchestrator_with_echo):
    orch, provider, audit, paths = orchestrator_with_echo
    payload = {
        "messages": [
            {"role": "user", "content": "Email me at jane.doe@example.com or call 415-555-0199."}
        ]
    }

    result = await orch.chat(payload)

    # The provider must never receive the raw PII.
    assert len(provider.seen_contexts) == 1
    seen_text = provider.seen_contexts[0].messages[-1].content
    assert "jane.doe@example.com" not in seen_text
    assert "415-555-0199" not in seen_text
    assert "[PII_TOKEN_" in seen_text

    # The client-facing response has the original PII values restored.
    assert "jane.doe@example.com" in result.content
    assert "415-555-0199" in result.content
    assert result.unresolved_tokens == []
    assert result.review_required is False

    # Intermediate steps are exposed for visibility (masked prompt + raw
    # pre-rehydration model output), and neither leaks/hides the expected way.
    assert "jane.doe@example.com" not in result.sanitized_prompt
    assert "[PII_TOKEN_" in result.sanitized_prompt
    assert "[PII_TOKEN_" in result.raw_model_output

    # A short reassurance system message precedes the user message when PII
    # was redacted (reduces model false-refusals on PII_TOKEN placeholders).
    assert len(provider.seen_contexts[0].messages) == 2
    assert provider.seen_contexts[0].messages[0].role == "system"
    assert result.difficulty == "simple"  # the notice must not inflate word-count classification


async def test_no_reassurance_notice_when_no_pii_present(orchestrator_with_echo):
    orch, provider, audit, paths = orchestrator_with_echo

    await orch.chat({"messages": [{"role": "user", "content": "hi there"}]})

    # No PII redacted -> no need for the notice, and no extra message.
    assert len(provider.seen_contexts[0].messages) == 1
    assert provider.seen_contexts[0].messages[0].role == "user"


async def test_difficulty_routes_to_different_models(orchestrator_with_echo):
    orch, provider, audit, paths = orchestrator_with_echo

    simple = await orch.chat({"messages": [{"role": "user", "content": "hi there"}]})
    complex_ = await orch.chat(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Design a thread-safe, async, distributed cache with unit tests "
                        "and error handling, and prove its correctness step by step."
                    ),
                }
            ]
        }
    )

    assert simple.difficulty == "simple"
    assert complex_.difficulty == "complex"
    assert simple.model_id != complex_.model_id


async def test_block_classified_content_is_rejected_and_audited(orchestrator_with_echo):
    orch, provider, audit, paths = orchestrator_with_echo
    payload = {"messages": [{"role": "user", "content": "My SSN is 123-45-6789, help me file taxes."}]}

    with pytest.raises(BlockedContentError) as excinfo:
        await orch.chat(payload)

    assert "GOV_ID" in excinfo.value.labels
    # The provider must never have been called at all.
    assert provider.seen_contexts == []

    audit.write(excinfo.value.audit_record)
    lines = _read_jsonl(paths["audit_log"])
    assert len(lines) == 1
    assert lines[0]["event"] == "blocked"
    assert lines[0]["blocked_labels"] == ["GOV_ID"]


async def test_duplicate_token_use_still_rehydrates_safely(tmp_paths):
    """A model reusing the same placeholder more than once (e.g. addressing
    someone by name twice) isn't actually ambiguous -- every repeat resolves
    to the same vaulted value -- so this must rehydrate cleanly instead of
    being flagged review_required, unlike a genuinely missing/unknown token."""
    guard = PiiGuard(vault_storage_path=tmp_paths["vault"])
    router = LiteRouter(DuplicatingStubProvider(), log_path=tmp_paths["router_log"])
    audit = AuditLogger(path=tmp_paths["audit_log"])
    orch = Orchestrator(guard, router, audit)

    result = await orch.chat({"messages": [{"role": "user", "content": "My name is Priya, say hi."}]})

    assert result.review_required is False
    assert result.unresolved_tokens == []
    assert result.content.count("Priya") == 2
    assert "[PII_TOKEN_" not in result.content

    await guard.close()


async def test_unresolved_tokens_surface_review_required_instead_of_failing(orchestrator_with_stub):
    """Plain StubProvider doesn't echo PII_TOKEN placeholders back, so the
    rehydration token count won't match -- this must not crash the request;
    it must come back with review_required=True and the raw model text."""
    orch, audit, paths = orchestrator_with_stub
    payload = {"messages": [{"role": "user", "content": "My email is a@b.com, say hi."}]}

    result = await orch.chat(payload)

    assert result.review_required is True
    assert result.content  # best-effort content still returned

    audit.write(result.audit_record)
    lines = _read_jsonl(paths["audit_log"])
    assert lines[0]["review_required"] is True


async def test_audit_log_has_one_well_formed_line_per_request(orchestrator_with_echo):
    orch, provider, audit, paths = orchestrator_with_echo

    for text in ("hi", "email a@b.com please", "write a function to reverse a list"):
        result = await orch.chat({"messages": [{"role": "user", "content": text}]})
        audit.write(result.audit_record)

    lines = _read_jsonl(paths["audit_log"])
    assert len(lines) == 3
    for line in lines:
        assert line["event"] == "completed"
        assert "request_id" in line and "session_id" in line
        assert "span_counts_by_label" in line
        assert "total_ms" in line and line["total_ms"] >= 0


def _read_jsonl(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]
