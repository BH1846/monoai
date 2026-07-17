"""G5 proof test: output-side scanning catches PII the model leaks that
was never present in the prompt (stub provider emits an SSN)."""
from detect.pipeline import DetectionPipeline
from pii import PiiEngine
from policy.store import PolicyStore
from vault.crypto import VaultCrypto
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


def test_model_leaked_ssn_is_redacted(tmp_path):
    pii = _engine(tmp_path)
    policy = _policy()
    session_id = "session-output-scan"

    # A stub provider "hallucinating" an SSN that was never in the prompt.
    raw_model_output = "Sure, here's a reference: SSN 123-45-6789 for the file."

    processed, output_token_ids = pii.scan_output(raw_model_output, session_id, policy)

    assert "123-45-6789" not in processed
    # SSN is GOV_ID -> BLOCK under default.yaml: no token minted (BLOCK
    # values are never vaulted), just a redaction marker.
    assert not output_token_ids
    assert "[REDACTED_OUTPUT_GOV_ID]" in processed

    # Rehydration must NOT restore the redacted value (it was never vaulted).
    final_text, unresolved, review_required = pii.rehydrate(processed, session_id, set(), set())
    assert "123-45-6789" not in final_text
    assert "[REDACTED_OUTPUT_GOV_ID]" in final_text


def test_model_leaked_email_is_tokenized_not_left_in_clear(tmp_path):
    pii = _engine(tmp_path)
    policy = _policy()
    session_id = "session-output-scan-2"

    raw_model_output = "You can also reach the backup contact at extra@example.com."
    processed, output_token_ids = pii.scan_output(raw_model_output, session_id, policy)

    assert "extra@example.com" not in processed
    assert len(output_token_ids) == 1
    # A response containing a type-labeled token, not the raw value -- exactly
    # what G5 requires. example.com isn't a common webmail domain, but the
    # format is type-labeled + opaque regardless of value.
    (token_id,) = output_token_ids
    assert f"<EMAIL_PII_{token_id}>" in processed


def test_existing_token_survives_real_onnx_output_scan(tmp_path):
    """Regression test for a real bug found during manual end-to-end
    smoke-testing: the real ONNX NER model can misclassify a token's own
    syntax as a fresh entity, producing two overlapping spans that each get
    independently re-tokenized -- corrupting a legitimate, already-issued
    placeholder into a garbled nested mess. scan_output must treat existing
    token ranges as protected from re-detection regardless of what any
    detector (including the fuzzy NER one) thinks it found there."""
    pipeline = DetectionPipeline(use_onnx_ner=True)
    crypto = VaultCrypto(_FakeRedis())
    vault = SqliteVaultStore(crypto, storage_path=str(tmp_path / "vault.sqlite"))
    pii = PiiEngine(pipeline, vault, "test-server-secret")
    policy = _policy()

    raw_model_output = "[simple] stub response to: Email me at <EMAIL_PII_78464d19db> about the invoice"
    processed, new_token_ids = pii.scan_output(raw_model_output, "session-onnx-guard", policy)

    assert processed == raw_model_output
    assert not new_token_ids


def test_include_ner_false_avoids_small_window_false_positive(tmp_path):
    """Regression test for a second real bug found during end-to-end
    smoke-testing: on a tiny out-of-context fragment (a streaming flush
    window), the real ONNX NER model hallucinated an entity from "mple"
    (the mid-word remainder of "[simple]" split across chunk boundaries),
    minting a bogus token for plain non-PII text. gateway/streaming.py
    passes include_ner=False for exactly this reason -- regex/secrets
    detectors remain reliable at any window size."""
    pipeline = DetectionPipeline(use_onnx_ner=True)
    crypto = VaultCrypto(_FakeRedis())
    vault = SqliteVaultStore(crypto, storage_path=str(tmp_path / "vault.sqlite"))
    pii = PiiEngine(pipeline, vault, "test-server-secret")
    policy = _policy()

    fragment = "mple"
    processed, new_token_ids = pii.scan_output(fragment, "session-ner-guard", policy, include_ner=False)

    assert processed == fragment
    assert not new_token_ids
