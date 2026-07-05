"""PostgresVaultStore: Phase 2 stub.

Multi-worker-safe production vault backend (asyncpg). Not implemented in
Phase 1 — see DECISIONS.md (SQLite-first for both vault and gateway/auth
key storage in Phase 1).
"""
from __future__ import annotations

from typing import Optional


class PostgresVaultStore:
    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError("postgres vault backend is Phase 2 — see DECISIONS.md")

    def write_async(self, session_id: str, token_id: str, plaintext: str) -> None:
        raise NotImplementedError("postgres vault backend is Phase 2 — see DECISIONS.md")

    def get(self, session_id: str, token_id: str) -> Optional[str]:
        raise NotImplementedError("postgres vault backend is Phase 2 — see DECISIONS.md")

    def close(self) -> None:
        raise NotImplementedError("postgres vault backend is Phase 2 — see DECISIONS.md")
