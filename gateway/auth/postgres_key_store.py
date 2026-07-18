"""PostgresKeyStore: production, multi-worker-safe virtual-key storage.

Sync (psycopg3, not asyncpg — see DECISIONS.md's `core/vault/storage/
postgres_store.py` precedent): `KeyStore.get_by_hash` et al are called
from within already-async auth middleware without an `await`, so a
sync driver matches the existing call shape without threading
async/await through every auth check.

Same schema/row shape as auth/store.py's SqliteKeyStore, so both are
drop-in behind the same `KeyStore` protocol -- kept as fully
independent implementations (no cross-import) rather than sharing a
private helper, matching core/vault/storage/'s sqlite/postgres split.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time

from auth.models import VirtualKey

_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS virtual_keys (
    key_id TEXT PRIMARY KEY,
    key_hash TEXT NOT NULL UNIQUE,
    team_id TEXT,
    policy_id TEXT NOT NULL,
    model_allowlist TEXT,
    budget_usd_monthly DOUBLE PRECISION,
    budget_usd_spent DOUBLE PRECISION NOT NULL,
    rate_limit_rps DOUBLE PRECISION NOT NULL,
    rate_limit_burst INTEGER NOT NULL,
    active BOOLEAN NOT NULL,
    created_at DOUBLE PRECISION NOT NULL,
    revoked_at DOUBLE PRECISION,
    origin_gateway TEXT,
    origin_callback_url TEXT
)
"""

_SELECT_COLUMNS = (
    "key_id, key_hash, team_id, policy_id, model_allowlist, budget_usd_monthly, "
    "budget_usd_spent, rate_limit_rps, rate_limit_burst, active, created_at, revoked_at, "
    "origin_gateway, origin_callback_url"
)


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


class PostgresKeyStore:
    def __init__(self, dsn: str) -> None:
        import psycopg

        self._conn = psycopg.connect(dsn, autocommit=True)
        self._conn.execute(_PG_SCHEMA)
        # In-place upgrade for a table created before the federation columns
        # (mirrors SqliteKeyStore._ensure_federation_columns). IF NOT EXISTS
        # makes it idempotent and safe on a fresh table too.
        self._conn.execute("ALTER TABLE virtual_keys ADD COLUMN IF NOT EXISTS origin_gateway TEXT")
        self._conn.execute("ALTER TABLE virtual_keys ADD COLUMN IF NOT EXISTS origin_callback_url TEXT")

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
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL)",
            (
                key.key_id, key.key_hash, key.team_id, key.policy_id,
                json.dumps(model_allowlist) if model_allowlist is not None else None,
                budget_usd_monthly, 0.0, rate_limit_rps, rate_limit_burst, True,
                key.created_at, None,
            ),
        )
        return raw_key, key

    def add_forwarded_key(self, key: VirtualKey) -> None:
        self._conn.execute(
            "INSERT INTO virtual_keys (key_id, key_hash, team_id, policy_id, model_allowlist, "
            "budget_usd_monthly, budget_usd_spent, rate_limit_rps, rate_limit_burst, active, "
            "created_at, revoked_at, origin_gateway, origin_callback_url) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (key_id) DO NOTHING",
            (
                key.key_id, key.key_hash, key.team_id, key.policy_id,
                json.dumps(key.model_allowlist) if key.model_allowlist is not None else None,
                key.budget_usd_monthly, key.budget_usd_spent, key.rate_limit_rps, key.rate_limit_burst,
                key.active, key.created_at, key.revoked_at, key.origin_gateway, key.origin_callback_url,
            ),
        )

    def get_by_hash(self, key_hash: str) -> VirtualKey | None:
        row = self._conn.execute(
            f"SELECT {_SELECT_COLUMNS} FROM virtual_keys WHERE key_hash = %s", (key_hash,)
        ).fetchone()
        return _row_to_key(row) if row else None

    def get_by_id(self, key_id: str) -> VirtualKey | None:
        row = self._conn.execute(
            f"SELECT {_SELECT_COLUMNS} FROM virtual_keys WHERE key_id = %s", (key_id,)
        ).fetchone()
        return _row_to_key(row) if row else None

    def update_budget_spent(self, key_id: str, budget_usd_spent: float) -> None:
        self._conn.execute(
            "UPDATE virtual_keys SET budget_usd_spent = %s WHERE key_id = %s",
            (budget_usd_spent, key_id),
        )

    def revoke(self, key_id: str) -> None:
        self._conn.execute(
            "UPDATE virtual_keys SET active = false, revoked_at = %s WHERE key_id = %s",
            (time.time(), key_id),
        )

    def list_keys(self, team_id: str | None = None) -> list[VirtualKey]:
        if team_id is None:
            rows = self._conn.execute(f"SELECT {_SELECT_COLUMNS} FROM virtual_keys").fetchall()
        else:
            rows = self._conn.execute(
                f"SELECT {_SELECT_COLUMNS} FROM virtual_keys WHERE team_id = %s", (team_id,)
            ).fetchall()
        return [_row_to_key(row) for row in rows]

    def close(self) -> None:
        self._conn.close()
