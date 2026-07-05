"""VaultStore protocol: pluggable backend (sqlite for dev, postgres for
prod — see DECISIONS.md for the Phase 1 SQLite-first choice)."""
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

    def close(self) -> None:
        ...
