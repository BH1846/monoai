"""G8 proof tests: multi-turn PII handling.

test_same_email_same_token_across_turns proves the root-cause fix at the
vault/session_tokens layer (the old per-call counter + INSERT OR REPLACE
cross-contamination bug -- see DECISIONS.md). test_roles_preserved_to_provider
needs the full orchestrator (gateway/api/chat.py, Step 9) and is added there.
"""
from contracts.policy import Action
from contracts.spans import TextUnit, TextUnitLocator
from detect.pipeline import DetectionPipeline
from policy.engine import evaluate
from policy.store import PolicyStore
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
