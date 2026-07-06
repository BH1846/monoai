"""VaultStore protocol: pluggable backend (sqlite for dev, postgres for
prod — see DECISIONS.md for the psycopg-not-asyncpg choice)."""
from __future__ import annotations

from typing import Optional, Protocol


class VaultStore(Protocol):
    def write_async(self, session_id: str, token_id: str, plaintext: str) -> None:
        """Non-blocking: encryption + disk write happen off the caller's
        critical path. Implementations should make the value readable via
        get() as soon as this returns (e.g. via an in-memory cache), even
        before the durable write lands."""
        ...

    def get(self, session_id: str, token_id: str) -> Optional[str]:
        ...

    def sweep_expired(self) -> int:
        """TTL sweeper: physically deletes expired entries. Returns the
        count removed."""
        ...

    def erase_session(self, session_id: str) -> int:
        """Right-to-erasure API (DPDP/GDPR): permanently deletes every
        entry for a session_id. Returns the count removed."""
        ...

    def close(self) -> None:
        ...
