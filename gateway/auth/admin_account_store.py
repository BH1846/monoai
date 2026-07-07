"""SqliteAdminAccountStore: remembers which admin API key belongs to which
admin email, so the console only has to be handed the key once per
deployment instead of once per browser session (see web/src/context/
GatewayContext.tsx). Encrypts the key at rest via the existing VaultCrypto
primitive (core/vault/crypto.py), same pattern as providers/registry_store.py.

Security note: lookup (GET /v1/admin/account/{email}) is intentionally
*not* gated behind the admin key -- that's the whole point, it's how the
console avoids asking for it again. That means anyone who can reach this
gateway and knows/guesses an admin's email can retrieve the admin key.
Saving a new mapping (POST /v1/admin/account) *is* gated: you must already
present a valid admin key to associate it with an email. Acceptable for a
single-operator local/dev deployment; would need real per-admin credentials
for anything multi-tenant.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

from nacl.exceptions import CryptoError
from typing import Optional

from vault.crypto import VaultCrypto

_AAD_NAMESPACE = "admin_account"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS admin_accounts (
    email TEXT PRIMARY KEY,
    admin_key_nonce BLOB NOT NULL,
    admin_key_ciphertext BLOB NOT NULL,
    admin_key_sealed_dek BLOB NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
)
"""


@dataclass
class AdminAccount:
    email: str
    admin_key: str
    created_at: float
    updated_at: float


class SqliteAdminAccountStore:
    def __init__(self, crypto: VaultCrypto, storage_path: str = "./gateway_admin_accounts.sqlite") -> None:
        self._crypto = crypto
        self._conn = sqlite3.connect(storage_path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def save(self, email: str, admin_key: str) -> None:
        now = time.time()
        nonce, ciphertext, sealed_dek = self._crypto.encrypt(_AAD_NAMESPACE, email, admin_key)
        existing = self._conn.execute(
            "SELECT created_at FROM admin_accounts WHERE email = ?", (email,)
        ).fetchone()
        created_at = existing[0] if existing else now
        self._conn.execute(
            "INSERT OR REPLACE INTO admin_accounts "
            "(email, admin_key_nonce, admin_key_ciphertext, admin_key_sealed_dek, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (email, nonce, ciphertext, sealed_dek, created_at, now),
        )
        self._conn.commit()

    def get(self, email: str) -> Optional[AdminAccount]:
        row = self._conn.execute(
            "SELECT admin_key_nonce, admin_key_ciphertext, admin_key_sealed_dek, created_at, updated_at "
            "FROM admin_accounts WHERE email = ?",
            (email,),
        ).fetchone()
        if row is None:
            return None
        nonce, ciphertext, sealed_dek, created_at, updated_at = row
        try:
            admin_key = self._crypto.decrypt(_AAD_NAMESPACE, email, nonce, ciphertext, sealed_dek)
        except CryptoError:
            # The vault's master key (Valkey-backed, no on-disk fallback --
            # see core/vault/crypto.py) no longer matches whatever encrypted
            # this row, e.g. Valkey data was lost/reset since it was saved.
            # The row is permanently unusable; treat it the same as "never
            # saved" so callers get a clean 404 telling the admin to just
            # save their key again, instead of a raw 500.
            return None
        return AdminAccount(email=email, admin_key=admin_key, created_at=created_at, updated_at=updated_at)

    def close(self) -> None:
        self._conn.close()
