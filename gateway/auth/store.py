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
    revoked_at REAL,
    origin_gateway TEXT,
    origin_callback_url TEXT
)
"""

# Column list shared by every SELECT so row order stays in lockstep with
# _row_to_key. The two federation columns are last so an ALTER-added column on
# a pre-existing DB lines up (SQLite appends added columns).
_COLS = (
    "key_id, key_hash, team_id, policy_id, model_allowlist, budget_usd_monthly, "
    "budget_usd_spent, rate_limit_rps, rate_limit_burst, active, created_at, revoked_at, "
    "origin_gateway, origin_callback_url"
)


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

    def get_by_id(self, key_id: str) -> VirtualKey | None:
        ...

    def add_forwarded_key(self, key: VirtualKey) -> None:
        """Insert a key created on a PEER gateway (key forwarding), preserving
        its original key_id/hash and origin_* provenance. Idempotent on
        key_id (a retried forward must not error/duplicate)."""
        ...

    def update_budget_spent(self, key_id: str, budget_usd_spent: float) -> None:
        ...

    def revoke(self, key_id: str) -> None:
        ...

    def list_keys(self, team_id: str | None = None) -> list[VirtualKey]:
        ...


def _row_to_key(row) -> VirtualKey:
    (key_id, key_hash, team_id, policy_id, model_allowlist_json, budget_usd_monthly,
     budget_usd_spent, rate_limit_rps, rate_limit_burst, active, created_at, revoked_at,
     origin_gateway, origin_callback_url) = row
    return VirtualKey(
        key_id=key_id, key_hash=key_hash, team_id=team_id, policy_id=policy_id,
        model_allowlist=json.loads(model_allowlist_json) if model_allowlist_json else None,
        budget_usd_monthly=budget_usd_monthly, budget_usd_spent=budget_usd_spent,
        rate_limit_rps=rate_limit_rps, rate_limit_burst=rate_limit_burst,
        active=bool(active), created_at=created_at, revoked_at=revoked_at,
        origin_gateway=origin_gateway, origin_callback_url=origin_callback_url,
    )


class SqliteKeyStore:
    def __init__(self, storage_path: str = "./gateway_keys.sqlite") -> None:
        self._conn = sqlite3.connect(storage_path, check_same_thread=False)
        self._conn.execute(_SCHEMA)
        self._ensure_federation_columns()
        self._conn.commit()

    def _ensure_federation_columns(self) -> None:
        """Add the origin_* columns to a virtual_keys table created before
        they existed. Mirrors core/vault/storage/sqlite_store.py's
        _ensure_expires_at_column so an existing gateway_keys.sqlite upgrades
        in place instead of a SELECT crashing on a missing column."""
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(virtual_keys)")}
        if "origin_gateway" not in existing:
            self._conn.execute("ALTER TABLE virtual_keys ADD COLUMN origin_gateway TEXT")
        if "origin_callback_url" not in existing:
            self._conn.execute("ALTER TABLE virtual_keys ADD COLUMN origin_callback_url TEXT")

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
            "created_at, revoked_at, origin_gateway, origin_callback_url) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)",
            (
                key.key_id, key.key_hash, key.team_id, key.policy_id,
                json.dumps(model_allowlist) if model_allowlist is not None else None,
                budget_usd_monthly, 0.0, rate_limit_rps, rate_limit_burst, 1,
                key.created_at, None,
            ),
        )
        self._conn.commit()
        return raw_key, key

    def add_forwarded_key(self, key: VirtualKey) -> None:
        # INSERT OR IGNORE on the PRIMARY KEY (key_id): a retried forward is a
        # no-op rather than an error, matching the at-least-once delivery model.
        self._conn.execute(
            f"INSERT OR IGNORE INTO virtual_keys ({_COLS}) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                key.key_id, key.key_hash, key.team_id, key.policy_id,
                json.dumps(key.model_allowlist) if key.model_allowlist is not None else None,
                key.budget_usd_monthly, key.budget_usd_spent, key.rate_limit_rps, key.rate_limit_burst,
                1 if key.active else 0, key.created_at, key.revoked_at,
                key.origin_gateway, key.origin_callback_url,
            ),
        )
        self._conn.commit()

    def get_by_hash(self, key_hash: str) -> VirtualKey | None:
        row = self._conn.execute(
            f"SELECT {_COLS} FROM virtual_keys WHERE key_hash = ?",
            (key_hash,),
        ).fetchone()
        return _row_to_key(row) if row else None

    def get_by_id(self, key_id: str) -> VirtualKey | None:
        row = self._conn.execute(
            f"SELECT {_COLS} FROM virtual_keys WHERE key_id = ?",
            (key_id,),
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
            rows = self._conn.execute(f"SELECT {_COLS} FROM virtual_keys").fetchall()
        else:
            rows = self._conn.execute(
                f"SELECT {_COLS} FROM virtual_keys WHERE team_id = ?", (team_id,)
            ).fetchall()
        return [_row_to_key(row) for row in rows]

    def close(self) -> None:
        self._conn.close()
