"""TransactionForwarder: forward per-user chat sessions (prompt/reply) from a
forwarding instance UP to the manager, so a user created on an instance shows
their full session drill-down in the manager's Users tab -- not just their key.

This is the sibling of audit/key forwarding, but it carries the MOST sensitive
data in the system: the raw prompt and reply. So the raw text is encrypted at
EVERY hop:

  * origin at rest  -- enqueue() encrypts the 4 text fields with THIS gateway's
    own VaultCrypto before they touch the durable forward queue, exactly like
    SqliteTransactionStore does on disk. The queue never holds plaintext.
  * in transit      -- at delivery the worker decrypts (in memory only) and
    RE-SEALS the blob to the manager with the authenticated PyNaCl Box
    (core/vault/box.py). Only the manager's private key can open it.
  * manager at rest -- the manager opens the Box and re-encrypts under its OWN
    VaultCrypto via transaction_store.record(). A forwarded session is stored
    identically to a local one.

Same durability/ordering/fail-open guarantees as the other forwarders:
enqueue() does no network I/O and never raises (it runs on the request path via
orchestrator._record_transaction); a background thread drains oldest-first,
acks only on a confirmed 2xx, and delivery is at-least-once so the manager
dedupes on request_id. A manager that's down just means sessions queue locally.
"""
from __future__ import annotations

import json
import logging
import threading
import time

import httpx
from vault.box import seal
from vault.crypto import VaultCrypto

logger = logging.getLogger(__name__)

_AAD_NAMESPACE = "txn_forward_queue"

# The plaintext text fields (sealed as one JSON blob); everything else is
# non-secret metadata carried in the clear.
_TEXT_FIELDS = ("original_prompt", "redacted_prompt", "llm_reply", "rehydrated_reply")


class TransactionForwarder:
    def __init__(
        self,
        crypto: VaultCrypto,
        origin_private_key_hex: str,
        origin_public_key_hex: str,
        gateway_id: str,
        ingest_url: str,
        pubkey_url: str,
        admin_key: str,
        queue,
        interval_s: float = 30.0,
        timeout: float = 5.0,
        batch_size: int = 100,
        start_worker: bool = True,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._crypto = crypto
        self._priv = origin_private_key_hex
        self._pub = origin_public_key_hex
        self._gateway_id = gateway_id
        self._ingest_url = ingest_url
        self._pubkey_url = pubkey_url
        self._queue = queue
        self._interval_s = interval_s
        self._batch_size = batch_size
        self._client = httpx.Client(
            timeout=timeout,
            headers={"Authorization": f"Bearer {admin_key}", "Content-Type": "application/json"},
            transport=transport,
        )
        self._manager_pubkey: str | None = None  # fetched + cached lazily
        self._wake = threading.Event()
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None
        if start_worker:
            self._thread = threading.Thread(target=self._run, name="txn-forwarder", daemon=True)
            self._thread.start()

    # -- request path (fast, never raises, no network) ---------------------

    def enqueue(self, *, request_id: str, session_id, team_id, virtual_key_id, model, status,
                redaction_rules, input_tokens, output_tokens, cost,
                original_prompt, redacted_prompt, llm_reply, rehydrated_reply) -> None:
        """Encrypt the raw text under THIS gateway's vault and durably queue the
        session for forwarding. No network I/O; never raises (the chat request
        has already completed -- forwarding is best-effort)."""
        try:
            text_blob = json.dumps({
                "original_prompt": original_prompt, "redacted_prompt": redacted_prompt,
                "llm_reply": llm_reply, "rehydrated_reply": rehydrated_reply,
            })
            nonce, ciphertext, sealed_dek = self._crypto.encrypt(_AAD_NAMESPACE, request_id, text_blob)
            payload = {
                "request_id": request_id, "session_id": session_id, "team_id": team_id,
                "virtual_key_id": virtual_key_id, "model": model, "status": status,
                "redaction_rules": redaction_rules, "input_tokens": input_tokens,
                "output_tokens": output_tokens, "cost": cost, "ts": time.time(),
                # raw text, encrypted at rest with the origin vault (hex-encoded)
                "enc_text": {"nonce": nonce.hex(), "ciphertext": ciphertext.hex(), "sealed_dek": sealed_dek.hex()},
            }
            self._queue.append(request_id, json.dumps(payload), time.time())
            self._wake.set()
        except Exception:  # noqa: BLE001 -- forwarding must never break a request
            logger.warning("failed to enqueue transaction for forwarding", exc_info=True)

    # -- background worker -------------------------------------------------

    def _run(self) -> None:  # pragma: no cover - exercised via drain_once in tests
        while not self._stopped.is_set():
            try:
                self.drain_once()
            except Exception:  # noqa: BLE001 -- the worker must never die
                logger.warning("transaction forwarding sweep failed", exc_info=True)
            self._wake.wait(self._interval_s)
            self._wake.clear()

    def _ensure_manager_pubkey(self) -> str | None:
        if self._manager_pubkey:
            return self._manager_pubkey
        try:
            resp = self._client.get(self._pubkey_url)
        except httpx.HTTPError:
            return None
        if resp.status_code >= 400:
            return None
        self._manager_pubkey = resp.json().get("pubkey")
        return self._manager_pubkey

    def drain_once(self) -> int:
        """Deliver queued sessions oldest-first; stop at the first failure to
        preserve order. Returns the count delivered."""
        manager_pubkey = self._ensure_manager_pubkey()
        if not manager_pubkey:
            return 0  # can't seal without it; leave everything queued
        delivered = 0
        while not self._stopped.is_set():
            batch = self._queue.peek_batch(self._batch_size)
            if not batch:
                break
            for item in batch:
                if not self._deliver(item.payload_json, manager_pubkey):
                    return delivered  # keep order; retry next sweep
                self._queue.ack([item.seq])
                delivered += 1
            if len(batch) < self._batch_size:
                break
        return delivered

    def _deliver(self, payload_json: str, manager_pubkey: str) -> bool:
        try:
            p = json.loads(payload_json)
            enc = p["enc_text"]
            # decrypt with the origin vault (in memory only)...
            text_blob = self._crypto.decrypt(
                _AAD_NAMESPACE, p["request_id"],
                bytes.fromhex(enc["nonce"]), bytes.fromhex(enc["ciphertext"]), bytes.fromhex(enc["sealed_dek"]),
            )
            # ...then Box-seal it to the manager for transit.
            nonce, ciphertext = seal(self._priv, manager_pubkey, text_blob)
        except Exception:  # noqa: BLE001 -- a corrupt/unopenable row must not wedge the queue
            logger.warning("transaction forward: dropping unprocessable queued session", exc_info=True)
            return True  # ack-drop; can never succeed

        body = {
            "request_id": p["request_id"], "session_id": p.get("session_id"), "team_id": p.get("team_id"),
            "virtual_key_id": p.get("virtual_key_id"), "model": p.get("model"), "status": p["status"],
            "redaction_rules": p.get("redaction_rules") or [], "input_tokens": p.get("input_tokens") or 0,
            "output_tokens": p.get("output_tokens") or 0, "cost": p.get("cost"), "ts": p.get("ts"),
            "origin_gateway": self._gateway_id, "origin_pubkey": self._pub,
            "sealed_text": {"nonce": nonce, "ciphertext": ciphertext},
        }
        try:
            resp = self._client.post(self._ingest_url, content=json.dumps(body))
        except httpx.HTTPError:
            return False
        return 200 <= resp.status_code < 300

    def close(self) -> None:
        self._stopped.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._client.close()
        close = getattr(self._queue, "close", None)
        if close is not None:
            close()
