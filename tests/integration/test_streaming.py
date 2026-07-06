"""G1 proof tests: SSE sliding-window rehydration."""
import time
from collections.abc import AsyncIterator

from detect.pipeline import DetectionPipeline
from pii import PiiEngine
from policy.store import PolicyStore
from streaming import HOLDBACK, StreamRehydrator
from vault.crypto import VaultCrypto
from vault.session_tokens import derive_session_key, make_token
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


def _engine(tmp_path) -> PiiEngine:
    pipeline = DetectionPipeline(use_onnx_ner=False)
    crypto = VaultCrypto(_FakeRedis())
    vault = SqliteVaultStore(crypto, storage_path=str(tmp_path / "vault.sqlite"))
    return PiiEngine(pipeline, vault, "test-server-secret")


def _policy():
    store = PolicyStore()
    store.load_dir("policies")
    return store.get("default")


async def _chunks(pieces: list[str]) -> AsyncIterator[str]:
    for piece in pieces:
        yield piece


async def test_token_split_across_chunks(tmp_path):
    pii = _engine(tmp_path)
    policy = _policy()
    session_id = "session-stream-1"
    session_key = derive_session_key(session_id, "test-server-secret")

    token = make_token(session_key, "a@b.com")  # e.g. "[PII_TOKEN_xxxxxxxxxx]"
    pii._vault.write_async(session_id, token[len("[PII_TOKEN_"):-1], "a@b.com")

    full_text = f"Sure, the email is {token} -- let me know if that works."
    # Split the token itself arbitrarily across 3 chunks (mid-bracket, mid-hex).
    split_a = full_text.index("[PII_TOKEN_") + 5
    split_b = split_a + 8
    pieces = [full_text[:split_a], full_text[split_a:split_b], full_text[split_b:]]

    input_token_ids = {token[len("[PII_TOKEN_"):-1]}
    rehydrator = StreamRehydrator(session_id, pii, policy, input_token_ids)

    result = ""
    async for piece in rehydrator.run(_chunks(pieces)):
        result += piece

    assert "a@b.com" in result
    assert "[PII_TOKEN_" not in result
    assert "UNRESOLVED" not in result


async def test_token_not_fragmented_across_many_small_chunks(tmp_path):
    """Regression test for a real bug found during manual end-to-end
    testing: with small, uniform chunk sizes (matching gateway/api/chat.py's
    real 4-char artificial chunking), a naive fixed-width holdback flushes
    a few bytes at a time and can fragment a token across THREE OR MORE
    separate _process() calls, each too small to regex-match a whole
    token -- so it's silently never rehydrated, even though every byte
    eventually arrives. The coarser 3-large-chunk test above didn't
    exercise this because each chunk alone already exceeded HOLDBACK."""
    pii = _engine(tmp_path)
    policy = _policy()
    session_id = "session-stream-fine-grained"
    session_key = derive_session_key(session_id, "test-server-secret")

    token = make_token(session_key, "415-555-0199")
    pii._vault.write_async(session_id, token[len("[PII_TOKEN_"):-1], "415-555-0199")

    full_text = f"[simple] stub response to: Call me at {token} please"
    pieces = [full_text[i:i + 4] for i in range(0, len(full_text), 4)]

    input_token_ids = {token[len("[PII_TOKEN_"):-1]}
    rehydrator = StreamRehydrator(session_id, pii, policy, input_token_ids)

    result = ""
    async for piece in rehydrator.run(_chunks(pieces)):
        result += piece

    assert "415-555-0199" in result
    assert "PII_TOKEN" not in result
    assert rehydrator.unresolved == []


async def test_ttfb_overhead(tmp_path):
    pii = _engine(tmp_path)
    policy = _policy()
    session_id = "session-stream-2"

    # First chunk alone exceeds HOLDBACK so it flushes immediately -- this
    # isolates our own processing overhead from any artificial wait.
    first_chunk = "x" * (HOLDBACK + 10)
    pieces = [first_chunk, " more text after"]

    async def baseline_upstream():
        for p in pieces:
            yield p

    t0 = time.monotonic()
    async for _ in baseline_upstream():
        break
    baseline_ttfb_ms = (time.monotonic() - t0) * 1000.0

    rehydrator = StreamRehydrator(session_id, pii, policy, set())
    t1 = time.monotonic()
    async for _ in rehydrator.run(_chunks(pieces)):
        break
    with_rehydration_ttfb_ms = (time.monotonic() - t1) * 1000.0

    assert with_rehydration_ttfb_ms - baseline_ttfb_ms < 60.0
    assert rehydrator.ttfb_ms is not None
