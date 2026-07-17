"""Agent offline buffer: append-only, ordered, ack-after-confirm semantics."""
from __future__ import annotations

from buffer import EventBuffer


def _buf(tmp_path) -> EventBuffer:
    return EventBuffer(str(tmp_path / "buffer.sqlite"))


def test_append_and_peek_in_production_order(tmp_path):
    b = _buf(tmp_path)
    for i in range(5):
        b.append(f'{{"n": {i}}}', created_at=float(i))
    batch = b.peek_batch(10)
    assert [e.payload_json for e in batch] == ['{"n": 0}', '{"n": 1}', '{"n": 2}', '{"n": 3}', '{"n": 4}']
    assert b.pending_count() == 5


def test_peek_does_not_remove(tmp_path):
    b = _buf(tmp_path)
    b.append("{}", 1.0)
    b.peek_batch(10)
    b.peek_batch(10)
    assert b.pending_count() == 1  # still there until acked


def test_ack_removes_only_confirmed(tmp_path):
    b = _buf(tmp_path)
    seqs = [b.append(f'{{"n": {i}}}', float(i)) for i in range(3)]
    b.ack(seqs[:2])
    remaining = b.peek_batch(10)
    assert len(remaining) == 1
    assert remaining[0].payload_json == '{"n": 2}'


def test_ordering_survives_restart(tmp_path):
    path = str(tmp_path / "buffer.sqlite")
    b = EventBuffer(path)
    b.append('{"n": 0}', 0.0)
    b.append('{"n": 1}', 1.0)
    b.close()
    # Reopen: seq autoincrement + WAL means order and content survive.
    b2 = EventBuffer(path)
    b2.append('{"n": 2}', 2.0)
    assert [e.payload_json for e in b2.peek_batch(10)] == ['{"n": 0}', '{"n": 1}', '{"n": 2}']
