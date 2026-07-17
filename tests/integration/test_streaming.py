"""G1 proof tests: SSE sliding-window rehydration."""
import time
from collections.abc import AsyncIterator

from detect.pipeline import DetectionPipeline
from pii import PiiEngine
from policy.store import PolicyStore
from streaming import HOLDBACK, StreamRehydrator
from vault.crypto import VaultCrypto
from vault.session_tokens import derive_session_key, make_token, make_token_id
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

    token_id = make_token_id(session_key, "a@b.com")
    token = make_token(session_key, "a@b.com", "EMAIL")  # "<EMAIL_PII_xxxxxxxxxx>"
    pii._vault.write_async(session_id, token_id, "a@b.com")

    full_text = f"Sure, the email is {token} -- let me know if that works."
    # Split the token itself arbitrarily across 3 chunks (mid-label, mid-hex).
    split_a = full_text.index(token) + 5
    split_b = split_a + 8
    pieces = [full_text[:split_a], full_text[split_a:split_b], full_text[split_b:]]

    input_token_ids = {token_id}
    rehydrator = StreamRehydrator(session_id, pii, policy, input_token_ids)

    result = ""
    async for piece in rehydrator.run(_chunks(pieces)):
        result += piece

    assert "a@b.com" in result
    assert "_PII_" not in result
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

    token_id = make_token_id(session_key, "415-555-0199")
    token = make_token(session_key, "415-555-0199", "PHONE")  # "<PHONE_PII_xxxxxxxxxx>"
    pii._vault.write_async(session_id, token_id, "415-555-0199")

    full_text = f"[simple] stub response to: Call me at {token} please"
    pieces = [full_text[i:i + 4] for i in range(0, len(full_text), 4)]

    input_token_ids = {token_id}
    rehydrator = StreamRehydrator(session_id, pii, policy, input_token_ids)

    result = ""
    async for piece in rehydrator.run(_chunks(pieces)):
        result += piece

    assert "415-555-0199" in result
    assert "_PII_" not in result
    assert rehydrator.unresolved == []


async def test_longest_token_type_streamed_one_char_at_a_time(tmp_path):
    """Variable-width regression: type-labeled tokens vary in length, and the
    LONGEST (<CREDIT_CARD_PII_...> / <DEMOGRAPHIC_PII_...>, 28 chars) is what
    the streaming holdback is sized for. Stream it one character at a time --
    the worst case for a fixed-width assumption -- and confirm it's still
    handed to _process whole and rehydrated exactly once."""
    pii = _engine(tmp_path)
    policy = _policy()
    session_id = "session-stream-longtok"
    session_key = derive_session_key(session_id, "test-server-secret")

    secret_value = "4111 1111 1111 1111"
    token_id = make_token_id(session_key, secret_value)
    token = make_token(session_key, secret_value, "CREDIT_CARD")  # 28 chars, the max width
    pii._vault.write_async(session_id, token_id, secret_value)

    full_text = f"On file: {token} (ends 1111)."
    pieces = list(full_text)  # one char per chunk

    rehydrator = StreamRehydrator(session_id, pii, policy, {token_id})
    result = "".join([p async for p in rehydrator.run(_chunks(pieces))])

    assert secret_value in result
    assert "_PII_" not in result
    assert rehydrator.unresolved == []


async def test_unrelated_angle_bracket_does_not_break_stream(tmp_path):
    """A literal '<' that is NOT a token opener (e.g. '5 < 10') must not
    strand text or fragment a real token later in the stream."""
    pii = _engine(tmp_path)
    policy = _policy()
    session_id = "session-stream-anglebracket"
    session_key = derive_session_key(session_id, "test-server-secret")

    token_id = make_token_id(session_key, "Priya")
    token = make_token(session_key, "Priya", "PERSON")
    pii._vault.write_async(session_id, token_id, "Priya")

    full_text = f"if 5 < 10 and x<y then greet {token} warmly"
    pieces = [full_text[i:i + 2] for i in range(0, len(full_text), 2)]

    rehydrator = StreamRehydrator(session_id, pii, policy, {token_id})
    result = "".join([p async for p in rehydrator.run(_chunks(pieces))])

    assert "greet Priya warmly" in result
    assert "5 < 10 and x<y" in result  # unrelated '<' preserved verbatim
    assert "_PII_" not in result
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
