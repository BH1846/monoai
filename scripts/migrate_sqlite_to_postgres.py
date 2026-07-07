#!/usr/bin/env python3
"""One-time structural migration: legacy SQLite vault/key-store files ->
production Postgres (core/vault/storage/postgres_store.py's
PostgresVaultStore, gateway/auth/postgres_key_store.py's
PostgresKeyStore).

Copies rows AS-IS -- vault entries are already encrypted
(nonce/ciphertext/sealed_dek), decryptable by whichever VaultCrypto
master key was used at write time; nothing here touches plaintext or
re-encrypts anything. Idempotent: re-running is safe, existing rows in
the destination are left alone (`ON CONFLICT DO NOTHING`).

Usage:
  python scripts/migrate_sqlite_to_postgres.py \\
      --vault-sqlite ./pii_vault.sqlite --vault-postgres-dsn postgresql://... \\
      --keystore-sqlite ./gateway_keys.sqlite --keystore-postgres-dsn postgresql://...

Either --vault-* or --keystore-* pair may be omitted to skip that migration.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys

_VAULT_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS vault_entries (
    session_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    nonce BYTEA NOT NULL,
    ciphertext BYTEA NOT NULL,
    sealed_dek BYTEA NOT NULL,
    created_at DOUBLE PRECISION NOT NULL,
    expires_at DOUBLE PRECISION,
    PRIMARY KEY (session_id, token_id)
)
"""

_KEY_STORE_PG_SCHEMA = """
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
    revoked_at DOUBLE PRECISION
)
"""


def _sqlite_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def migrate_vault(sqlite_path: str, postgres_dsn: str) -> tuple[int, int]:
    """Returns (attempted, actually_inserted). A pre-existing vault.sqlite
    from before G11's TTL column landed won't have `expires_at` at all
    -- SqliteVaultStore._ensure_expires_at_column() backfills it lazily
    on open, but a file migrated directly here might never have gone
    through that path, so we handle its absence explicitly rather than
    letting the SELECT fail outright."""
    import psycopg

    src = sqlite3.connect(sqlite_path)
    has_expires_at = "expires_at" in _sqlite_columns(src, "vault_entries")
    expires_col = "expires_at" if has_expires_at else "NULL as expires_at"
    rows = src.execute(
        f"SELECT session_id, token_id, nonce, ciphertext, sealed_dek, created_at, {expires_col} "
        "FROM vault_entries"
    ).fetchall()
    src.close()

    dst = psycopg.connect(postgres_dsn, autocommit=True)
    dst.execute(_VAULT_PG_SCHEMA)
    inserted = 0
    for session_id, token_id, nonce, ciphertext, sealed_dek, created_at, expires_at in rows:
        cur = dst.execute(
            "INSERT INTO vault_entries (session_id, token_id, nonce, ciphertext, sealed_dek, created_at, expires_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (session_id, token_id) DO NOTHING",
            (session_id, token_id, nonce, ciphertext, sealed_dek, created_at, expires_at),
        )
        inserted += cur.rowcount
    dst.close()
    return len(rows), inserted


def migrate_key_store(sqlite_path: str, postgres_dsn: str) -> tuple[int, int]:
    import psycopg

    src = sqlite3.connect(sqlite_path)
    rows = src.execute(
        "SELECT key_id, key_hash, team_id, policy_id, model_allowlist, budget_usd_monthly, "
        "budget_usd_spent, rate_limit_rps, rate_limit_burst, active, created_at, revoked_at "
        "FROM virtual_keys"
    ).fetchall()
    src.close()

    dst = psycopg.connect(postgres_dsn, autocommit=True)
    dst.execute(_KEY_STORE_PG_SCHEMA)
    inserted = 0
    for row in rows:
        (key_id, key_hash, team_id, policy_id, model_allowlist, budget_usd_monthly,
         budget_usd_spent, rate_limit_rps, rate_limit_burst, active, created_at, revoked_at) = row
        cur = dst.execute(
            "INSERT INTO virtual_keys (key_id, key_hash, team_id, policy_id, model_allowlist, "
            "budget_usd_monthly, budget_usd_spent, rate_limit_rps, rate_limit_burst, active, "
            "created_at, revoked_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (key_id) DO NOTHING",
            (key_id, key_hash, team_id, policy_id, model_allowlist, budget_usd_monthly,
             budget_usd_spent, rate_limit_rps, rate_limit_burst, bool(active), created_at, revoked_at),
        )
        inserted += cur.rowcount
    dst.close()
    return len(rows), inserted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--vault-sqlite", help="path to the legacy pii_vault.sqlite")
    parser.add_argument("--vault-postgres-dsn", help="destination Postgres DSN for vault entries")
    parser.add_argument("--keystore-sqlite", help="path to the legacy gateway_keys.sqlite")
    parser.add_argument("--keystore-postgres-dsn", help="destination Postgres DSN for virtual keys")
    args = parser.parse_args()

    if not args.vault_sqlite and not args.keystore_sqlite:
        print("nothing to migrate: pass --vault-sqlite and/or --keystore-sqlite", file=sys.stderr)
        return 2

    if args.vault_sqlite:
        if not args.vault_postgres_dsn:
            print("--vault-sqlite requires --vault-postgres-dsn", file=sys.stderr)
            return 2
        attempted, inserted = migrate_vault(args.vault_sqlite, args.vault_postgres_dsn)
        print(f"vault: {inserted}/{attempted} entries migrated ({attempted - inserted} already present)")

    if args.keystore_sqlite:
        if not args.keystore_postgres_dsn:
            print("--keystore-sqlite requires --keystore-postgres-dsn", file=sys.stderr)
            return 2
        attempted, inserted = migrate_key_store(args.keystore_sqlite, args.keystore_postgres_dsn)
        print(f"key store: {inserted}/{attempted} keys migrated ({attempted - inserted} already present)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
