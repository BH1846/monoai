"""SqliteForwardQueue: durable, order-preserving, ack-after-confirm."""
from __future__ import annotations

from audit.forward_queue import SqliteForwardQueue


def _queue(tmp_path) -> SqliteForwardQueue:
    return SqliteForwardQueue(str(tmp_path / "forward.sqlite"))


def test_append_and_peek_in_production_order(tmp_path):
    q = _queue(tmp_path)
    for i in range(5):
        q.append(f"rec{i}", f'{{"n": {i}}}', created_at=float(i))
    assert [r.record_id for r in q.peek_batch(10)] == ["rec0", "rec1", "rec2", "rec3", "rec4"]
    assert q.pending_count() == 5


def test_peek_does_not_remove(tmp_path):
    q = _queue(tmp_path)
    q.append("rec0", "{}", 1.0)
    q.peek_batch(10)
    q.peek_batch(10)
    assert q.pending_count() == 1  # stays until explicitly acked


def test_ack_removes_only_confirmed(tmp_path):
    q = _queue(tmp_path)
    seqs = [q.append(f"rec{i}", f'{{"n": {i}}}', float(i)) for i in range(3)]
    q.ack(seqs[:2])
    remaining = q.peek_batch(10)
    assert [r.record_id for r in remaining] == ["rec2"]


def test_order_and_content_survive_restart(tmp_path):
    path = str(tmp_path / "forward.sqlite")
    q = SqliteForwardQueue(path)
    q.append("rec0", '{"n": 0}', 0.0)
    q.append("rec1", '{"n": 1}', 1.0)
    q.close()

    # seq is AUTOINCREMENT, so ordering continues correctly after a restart.
    q2 = SqliteForwardQueue(path)
    q2.append("rec2", '{"n": 2}', 2.0)
    assert [r.record_id for r in q2.peek_batch(10)] == ["rec0", "rec1", "rec2"]
