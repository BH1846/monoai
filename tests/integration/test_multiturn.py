"""G8 proof tests: multi-turn PII handling.

test_same_email_same_token_across_turns proves the root-cause fix at the
vault/session_tokens layer (the old per-call counter + INSERT OR REPLACE
cross-contamination bug -- see DECISIONS.md). test_roles_preserved_to_provider
proves the full orchestrator no longer collapses a multi-turn conversation
into one synthetic user message (the old workaround this fix retires).
"""
from audit.chain import AuditChain
from audit.sinks import JsonlSink
from contracts.policy import Action
from contracts.spans import TextUnit, TextUnitLocator
from detect.pipeline import DetectionPipeline
from orchestrator import Orchestrator
from pii import PiiEngine
from policy.engine import evaluate
from policy.store import PolicyStore
from providers.base import ProviderAdapter
from providers.fallback_chain import FallbackChain, Route
from router.contracts import ProviderResponse, RequestContext
from vault.crypto import VaultCrypto
from vault.session_tokens import derive_session_key, make_token_id
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


def _unit(text: str, turn_index: int) -> TextUnit:
    return TextUnit(
        unit_id=f"u{turn_index}", role="user", text=text,
        locator=TextUnitLocator(surface="chat_message", path=f"messages[{turn_index}].content"),
        turn_index=turn_index, direction="input",
    )


def _sanitize_turn(text, turn_index, session_id, session_key, pipeline, policy, store):
    spans = pipeline.run([_unit(text, turn_index)])
    decisions = evaluate(spans, policy)
    tokens = {}
    for decision in decisions:
        if decision.action != Action.REVERSIBLE:
            continue
        token_id = make_token_id(session_key, decision.span.text)
        store.write_async(session_id, token_id, decision.span.text)
        tokens[token_id] = decision.span.text
    return tokens


def test_same_email_same_token_across_turns(tmp_path):
    pipeline = DetectionPipeline(use_onnx_ner=False)
    policy_store = PolicyStore()
    policy_store.load_dir("policies")
    policy = policy_store.get("default")

    crypto = VaultCrypto(_FakeRedis())
    vault = SqliteVaultStore(crypto, storage_path=str(tmp_path / "vault.sqlite"))

    session_id = "session-abc"
    session_key = derive_session_key(session_id, "test-server-secret")

    turn1_tokens = _sanitize_turn(
        "email me at a@b.com about the invoice", 0, session_id, session_key, pipeline, policy, vault
    )
    turn3_tokens = _sanitize_turn(
        "following up: still waiting on a@b.com", 2, session_id, session_key, pipeline, policy, vault
    )
    vault.flush()

    assert set(turn1_tokens) == set(turn3_tokens), "same email must produce the same token_id across turns"
    (token_id,) = turn1_tokens.keys()
    assert vault.get(session_id, token_id) == "a@b.com"

    # Exactly one vault entry exists for this value -- not a second one
    # silently created by a re-used counter index (the old collision bug).
    assert len(turn1_tokens) == 1


class _RecordingProvider(ProviderAdapter):
    def __init__(self) -> None:
        self.seen_contexts: list[RequestContext] = []

    async def complete(self, request_id: str, model_id: str, ctx: RequestContext) -> ProviderResponse:
        self.seen_contexts.append(ctx)
        return ProviderResponse(
            request_id=request_id, model_id=model_id, provider="recording", content="ok",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}, latency_ms=1.0,
        )


async def test_roles_preserved_to_provider(tmp_path):
    pipeline = DetectionPipeline(use_onnx_ner=False)
    crypto = VaultCrypto(_FakeRedis())
    vault = SqliteVaultStore(crypto, storage_path=str(tmp_path / "vault.sqlite"))
    pii = PiiEngine(pipeline, vault, "test-server-secret")

    policy_store = PolicyStore()
    policy_store.load_dir("policies")

    provider = _RecordingProvider()
    routes_by_tier = {
        tier: [Route(provider=provider, model_id=tier, provider_name="test")]
        for tier in ("simple", "moderate", "complex")
    }
    fallback_chain = FallbackChain(routes_by_tier, max_retries_per_route=0)
    audit_chain = AuditChain(JsonlSink(str(tmp_path / "audit.jsonl")))
    orch = Orchestrator(pii, policy_store, fallback_chain, audit_chain, {}, {})

    payload = {
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "My email is a@b.com"},
            {"role": "assistant", "content": "Got it, I'll use that email."},
            {"role": "user", "content": "Thanks, please confirm."},
        ]
    }

    await orch.chat(payload, session_id="session-roles")

    ctx = provider.seen_contexts[0]
    # 4 original messages + 1 reassurance system notice (PII was tokenized)
    # -- NOT collapsed into a single synthetic user message.
    assert len(ctx.messages) == 5
    roles = [m.role for m in ctx.messages]
    assert roles == ["system", "system", "user", "assistant", "user"]
    assert roles.count("user") == 2
    assert roles.count("assistant") == 1
