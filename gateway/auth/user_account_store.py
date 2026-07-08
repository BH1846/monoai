"""SqliteUserAccountStore: real end-user accounts (email + password), each
bound 1:1 to a virtual key created at registration time (see
gateway/api/auth.py POST /v1/auth/register) -- so signing up is sufficient
to start calling the gateway, with no admin action required. The admin
still sees every one of these keys via the existing GET /v1/admin/keys
(Users tab), since each key's team_id is set to the owning email.

Password hashing uses PyNaCl's pwhash (argon2id) -- already a project
dependency via core/vault/crypto.py, no new library needed. The virtual
key itself is encrypted at rest via the existing VaultCrypto primitive,
same pattern as auth/admin_account_store.py, so a successful login can
hand the raw key back to the browser (virtual_keys only ever stores a
hash, see auth/store.py, so this is the one place the raw secret survives
a server restart for the user to retrieve again).
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import Optional

import nacl.pwhash
from nacl.exceptions import CryptoError, InvalidkeyError

from vault.crypto import VaultCrypto

_AAD_NAMESPACE = "user_account"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_accounts (
    email TEXT PRIMARY KEY,
    password_hash BLOB NOT NULL,
    key_id TEXT NOT NULL,
    virtual_key_nonce BLOB NOT NULL,
    virtual_key_ciphertext BLOB NOT NULL,
    virtual_key_sealed_dek BLOB NOT NULL,
    created_at REAL NOT NULL
)
"""


@dataclass
class UserAccount:
    email: str
    key_id: str
    virtual_key: str
    created_at: float


class EmailAlreadyRegisteredError(ValueError):
    pass


class SqliteUserAccountStore:
    def __init__(self, crypto: VaultCrypto, storage_path: str = "./gateway_user_accounts.sqlite") -> None:
        self._crypto = crypto
        self._conn = sqlite3.connect(storage_path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def exists(self, email: str) -> bool:
        row = self._conn.execute("SELECT 1 FROM user_accounts WHERE email = ?", (email,)).fetchone()
        return row is not None

    def register(self, email: str, password: str, key_id: str, virtual_key: str) -> UserAccount:
        if self.exists(email):
            raise EmailAlreadyRegisteredError(email)
        password_hash = nacl.pwhash.str(password.encode("utf-8"))
        nonce, ciphertext, sealed_dek = self._crypto.encrypt(_AAD_NAMESPACE, email, virtual_key)
        created_at = time.time()
        self._conn.execute(
            "INSERT INTO user_accounts (email, password_hash, key_id, virtual_key_nonce, "
            "virtual_key_ciphertext, virtual_key_sealed_dek, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (email, password_hash, key_id, nonce, ciphertext, sealed_dek, created_at),
        )
        self._conn.commit()
        return UserAccount(email=email, key_id=key_id, virtual_key=virtual_key, created_at=created_at)

    def authenticate(self, email: str, password: str) -> Optional[UserAccount]:
        row = self._conn.execute(
            "SELECT password_hash, key_id, virtual_key_nonce, virtual_key_ciphertext, "
            "virtual_key_sealed_dek, created_at FROM user_accounts WHERE email = ?",
            (email,),
        ).fetchone()
        if row is None:
            return None
        password_hash, key_id, nonce, ciphertext, sealed_dek, created_at = row
        try:
            nacl.pwhash.verify(bytes(password_hash), password.encode("utf-8"))
        except InvalidkeyError:
            return None
        try:
            virtual_key = self._crypto.decrypt(_AAD_NAMESPACE, email, nonce, ciphertext, sealed_dek)
        except CryptoError:
            # Same failure mode as SqliteAdminAccountStore.get: the vault's
            # master key no longer matches whatever encrypted this row (e.g.
            # Valkey data was lost/reset). The row is unusable; treat it as
            # "no account" rather than a raw 500.
            return None
        return UserAccount(email=email, key_id=key_id, virtual_key=virtual_key, created_at=created_at)

    def close(self) -> None:
        self._conn.close()
