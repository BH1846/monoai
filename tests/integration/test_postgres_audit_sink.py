"""G10/G11 proof test: Postgres audit sink. Needs a live Postgres --
skips gracefully if TEST_POSTGRES_DSN isn't set or unreachable (same
pattern as this repo's Valkey dependency: real infra, not mocked, but
not required for the rest of the suite to pass).
"""
import os
import uuid

import pytest

from contracts.audit import AuditRecord

DSN = os.environ.get("TEST_POSTGRES_DSN", "postgresql://monoai:monoai@127.0.0.1:5433/monoai")


def _postgres_available() -> bool:
    try:
        import psycopg

        with psycopg.connect(DSN, connect_timeout=2):
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _postgres_available(), reason="no live Postgres at TEST_POSTGRES_DSN")


def test_postgres_sink_write_and_read_round_trip():
    from audit.sinks import PostgresSink

    table = f"audit_records_test_{uuid.uuid4().hex[:8]}"
    sink = PostgresSink(DSN, table=table)
    try:
        record = AuditRecord(
            ts=1.0, request_id="r1", session_id="s1", event="completed",
            policy_id="default", policy_version="sha256:abc",
        )
        sink.write(record)
        records = sink.read_all()
        assert len(records) == 1
        assert records[0].request_id == "r1"
    finally:
        sink._conn.execute(f"DROP TABLE IF EXISTS {table}")
        sink.close()
