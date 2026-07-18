"""SqliteTransactionStore: per-request record of a user's actual prompt and
the model's reply, so an admin can drill into any virtual key (Users tab ->
click a user) and see the real Original -> Redacted -> Reply -> Rehydrated
flow for each request, plus which redaction rules fired.

Unlike the audit chain (core/audit -- labels and counts only, never raw
values), this store DOES persist the raw prompt/reply text, because that is
exactly what the per-user inspection view shows. That text is therefore the
most sensitive data the gateway holds, so the four text fields are stored as
a single AES-GCM + sealed-box envelope-encrypted blob at rest via the same
VaultCrypto primitive (core/vault/crypto.py) used for provider API keys and
admin keys -- never plaintext on disk. Only queryable metadata (team, key,
model, token/cost counts, status, rule labels, timestamp) is stored in the
clear so the admin API can filter/sort without decrypting every row.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass

from nacl.exceptions import CryptoError
from vault.crypto import VaultCrypto

_AAD_NAMESPACE = "user_transaction"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    request_id      TEXT PRIMARY KEY,
    session_id      TEXT,
    ts              REAL NOT NULL,
    team_id         TEXT,
    virtual_key_id  TEXT,
    model           TEXT,
    status          TEXT NOT NULL,
    redaction_rules TEXT,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cost            REAL,
    blob_nonce      BLOB NOT NULL,
    blob_ciphertext BLOB NOT NULL,
    blob_sealed_dek BLOB NOT NULL,
    origin_gateway  TEXT
);
CREATE INDEX IF NOT EXISTS idx_tx_team ON transactions(team_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_tx_key ON transactions(virtual_key_id, ts DESC);
"""


@dataclass
class Transaction:
    request_id: str
    session_id: str | None
    ts: float
    team_id: str | None
    virtual_key_id: str | None
    model: str | None
    status: str  # "clean" | "redacted" | "blocked"
    redaction_rules: list[str]
    input_tokens: int
    output_tokens: int
    cost: float | None
    original_prompt: str
    redacted_prompt: str
    llm_reply: str
    rehydrated_reply: str
    # None = recorded on THIS gateway; set = forwarded in from a peer gateway
    # (session federation). The raw text was Box-sealed in transit and is
    # re-encrypted here under this gateway's own VaultCrypto, same as a local
    # row -- so a forwarded session is at-rest-encrypted identically.
    origin_gateway: str | None = None


class SqliteTransactionStore:
    def __init__(self, crypto: VaultCrypto, storage_path: str = "./gateway_transactions.sqlite") -> None:
        self._crypto = crypto
        self._conn = sqlite3.connect(storage_path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        # Migration: a transactions DB created before session_id existed won't
        # have the column (CREATE TABLE IF NOT EXISTS leaves it as-is). Add it
        # so session grouping works without dropping old rows.
        cols = [r[1] for r in self._conn.execute("PRAGMA table_info(transactions)")]
        if "session_id" not in cols:
            self._conn.execute("ALTER TABLE transactions ADD COLUMN session_id TEXT")
        if "origin_gateway" not in cols:
            self._conn.execute("ALTER TABLE transactions ADD COLUMN origin_gateway TEXT")
        # Created after the migration above so it works on both fresh DBs and
        # ones upgraded from the pre-session_id schema.
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_tx_session ON transactions(session_id, ts)")
        self._conn.commit()

    def record(
        self,
        *,
        request_id: str,
        session_id: str | None,
        team_id: str | None,
        virtual_key_id: str | None,
        model: str | None,
        status: str,
        redaction_rules: list[str],
        input_tokens: int,
        output_tokens: int,
        cost: float | None,
        original_prompt: str,
        redacted_prompt: str,
        llm_reply: str,
        rehydrated_reply: str,
        origin_gateway: str | None = None,
        ts: float | None = None,
    ) -> None:
        payload = json.dumps({
            "original_prompt": original_prompt,
            "redacted_prompt": redacted_prompt,
            "llm_reply": llm_reply,
            "rehydrated_reply": rehydrated_reply,
        })
        nonce, ciphertext, sealed_dek = self._crypto.encrypt(_AAD_NAMESPACE, request_id, payload)
        self._conn.execute(
            "INSERT OR REPLACE INTO transactions "
            "(request_id, session_id, ts, team_id, virtual_key_id, model, status, redaction_rules, "
            " input_tokens, output_tokens, cost, blob_nonce, blob_ciphertext, blob_sealed_dek, origin_gateway) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                request_id, session_id, ts if ts is not None else time.time(), team_id, virtual_key_id, model, status,
                json.dumps(redaction_rules), input_tokens, output_tokens, cost,
                nonce, ciphertext, sealed_dek, origin_gateway,
            ),
        )
        self._conn.commit()

    def list_transactions(
        self, *, team_id: str | None = None, virtual_key_id: str | None = None, limit: int = 100
    ) -> list[Transaction]:
        """Newest-first. Filters by virtual_key_id if given, else team_id, else
        returns the most recent across all users."""
        where, params = "", []
        if virtual_key_id is not None:
            where, params = "WHERE virtual_key_id = ?", [virtual_key_id]
        elif team_id is not None:
            where, params = "WHERE team_id = ?", [team_id]
        rows = self._conn.execute(
            "SELECT request_id, session_id, ts, team_id, virtual_key_id, model, status, redaction_rules, "
            "input_tokens, output_tokens, cost, blob_nonce, blob_ciphertext, blob_sealed_dek, origin_gateway "
            f"FROM transactions {where} ORDER BY ts DESC LIMIT ?",
            (*params, limit),
        ).fetchall()

        out: list[Transaction] = []
        for r in rows:
            (request_id, session_id, ts, team, vk, model, status, rules_json,
             in_tok, out_tok, cost, nonce, ct, dek, origin_gateway) = r
            try:
                blob = json.loads(self._crypto.decrypt(_AAD_NAMESPACE, request_id, nonce, ct, dek))
            except (CryptoError, ValueError):
                # Master key rotated/lost since this row was written -- the
                # text is unrecoverable. Surface the metadata with empty text
                # rather than 500-ing the whole listing on one bad row.
                blob = {}
            out.append(Transaction(
                request_id=request_id, session_id=session_id, ts=ts, team_id=team, virtual_key_id=vk, model=model,
                status=status, redaction_rules=json.loads(rules_json) if rules_json else [],
                input_tokens=in_tok or 0, output_tokens=out_tok or 0, cost=cost,
                original_prompt=blob.get("original_prompt", ""),
                redacted_prompt=blob.get("redacted_prompt", ""),
                llm_reply=blob.get("llm_reply", ""),
                rehydrated_reply=blob.get("rehydrated_reply", ""),
                origin_gateway=origin_gateway,
            ))
        return out

    def close(self) -> None:
        self._conn.close()
