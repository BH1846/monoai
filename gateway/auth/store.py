"""KeyStore: virtual API keys. SQLite here for dev/single-node (matches
core/vault's SQLite-first choice); see auth/postgres_key_store.py for
the production Postgres backend.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from typing import Protocol

from auth.models import VirtualKey

_SCHEMA = """
CREATE TABLE IF NOT EXISTS virtual_keys (
    key_id TEXT PRIMARY KEY,
    key_hash TEXT NOT NULL UNIQUE,
    team_id TEXT,
    policy_id TEXT NOT NULL,
    model_allowlist TEXT,
    budget_usd_monthly REAL,
    budget_usd_spent REAL NOT NULL,
    rate_limit_rps REAL NOT NULL,
    rate_limit_burst INTEGER NOT NULL,
    active INTEGER NOT NULL,
    created_at REAL NOT NULL,
    revoked_at REAL
)
"""


class KeyStore(Protocol):
    def create_key(
        self,
        team_id: str | None = None,
        policy_id: str = "default",
        model_allowlist: list[str] | None = None,
        budget_usd_monthly: float | None = None,
        rate_limit_rps: float = 5.0,
        rate_limit_burst: int = 20,
    ) -> tuple[str, VirtualKey]:
        ...

    def get_by_hash(self, key_hash: str) -> VirtualKey | None:
        ...

    def update_budget_spent(self, key_id: str, budget_usd_spent: float) -> None:
        ...

    def revoke(self, key_id: str) -> None:
        ...

    def list_keys(self, team_id: str | None = None) -> list[VirtualKey]:
        ...


def _row_to_key(row) -> VirtualKey:
    (key_id, key_hash, team_id, policy_id, model_allowlist_json, budget_usd_monthly,
     budget_usd_spent, rate_limit_rps, rate_limit_burst, active, created_at, revoked_at) = row
    return VirtualKey(
        key_id=key_id, key_hash=key_hash, team_id=team_id, policy_id=policy_id,
        model_allowlist=json.loads(model_allowlist_json) if model_allowlist_json else None,
        budget_usd_monthly=budget_usd_monthly, budget_usd_spent=budget_usd_spent,
        rate_limit_rps=rate_limit_rps, rate_limit_burst=rate_limit_burst,
        active=bool(active), created_at=created_at, revoked_at=revoked_at,
    )


class SqliteKeyStore:
    def __init__(self, storage_path: str = "./gateway_keys.sqlite") -> None:
        self._conn = sqlite3.connect(storage_path, check_same_thread=False)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def create_key(
        self,
        team_id: str | None = None,
        policy_id: str = "default",
        model_allowlist: list[str] | None = None,
        budget_usd_monthly: float | None = None,
        rate_limit_rps: float = 5.0,
        rate_limit_burst: int = 20,
    ) -> tuple[str, VirtualKey]:
        raw_key = "mk-" + secrets.token_hex(16)
        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        key_id = "vk_" + key_hash[:12]
        key = VirtualKey(
            key_id=key_id, key_hash=key_hash, team_id=team_id, policy_id=policy_id,
            model_allowlist=model_allowlist, budget_usd_monthly=budget_usd_monthly,
            budget_usd_spent=0.0, rate_limit_rps=rate_limit_rps, rate_limit_burst=rate_limit_burst,
            active=True,
        )
        self._conn.execute(
            "INSERT INTO virtual_keys (key_id, key_hash, team_id, policy_id, model_allowlist, "
            "budget_usd_monthly, budget_usd_spent, rate_limit_rps, rate_limit_burst, active, "
            "created_at, revoked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                key.key_id, key.key_hash, key.team_id, key.policy_id,
                json.dumps(model_allowlist) if model_allowlist is not None else None,
                budget_usd_monthly, 0.0, rate_limit_rps, rate_limit_burst, 1,
                key.created_at, None,
            ),
        )
        self._conn.commit()
        return raw_key, key

    def get_by_hash(self, key_hash: str) -> VirtualKey | None:
        row = self._conn.execute(
            "SELECT key_id, key_hash, team_id, policy_id, model_allowlist, budget_usd_monthly, "
            "budget_usd_spent, rate_limit_rps, rate_limit_burst, active, created_at, revoked_at "
            "FROM virtual_keys WHERE key_hash = ?",
            (key_hash,),
        ).fetchone()
        return _row_to_key(row) if row else None

    def update_budget_spent(self, key_id: str, budget_usd_spent: float) -> None:
        self._conn.execute(
            "UPDATE virtual_keys SET budget_usd_spent = ? WHERE key_id = ?",
            (budget_usd_spent, key_id),
        )
        self._conn.commit()

    def revoke(self, key_id: str) -> None:
        self._conn.execute(
            "UPDATE virtual_keys SET active = 0, revoked_at = ? WHERE key_id = ?",
            (time.time(), key_id),
        )
        self._conn.commit()

    def list_keys(self, team_id: str | None = None) -> list[VirtualKey]:
        if team_id is None:
            rows = self._conn.execute(
                "SELECT key_id, key_hash, team_id, policy_id, model_allowlist, budget_usd_monthly, "
                "budget_usd_spent, rate_limit_rps, rate_limit_burst, active, created_at, revoked_at "
                "FROM virtual_keys"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT key_id, key_hash, team_id, policy_id, model_allowlist, budget_usd_monthly, "
                "budget_usd_spent, rate_limit_rps, rate_limit_burst, active, created_at, revoked_at "
                "FROM virtual_keys WHERE team_id = ?",
                (team_id,),
            ).fetchall()
        return [_row_to_key(row) for row in rows]

    def close(self) -> None:
        self._conn.close()
