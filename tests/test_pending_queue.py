# SPDX-License-Identifier: GPL-3.0-or-later

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from kitsune.storage.pending_queue import PendingQueue
from kitsune.storage.pending_queue import (
    OP_ADD_FAVORITE,
    OP_ADD_COLLECTION,
    OP_SAVE_TIMECODE,
)


def test_load_nonexistent_file_returns_empty_queue(tmp_path):
    path = tmp_path / 'pending_ops.json'
    q = PendingQueue.load(path)
    assert q.size() == 0


def test_load_malformed_json_returns_empty_queue(tmp_path):
    path = tmp_path / 'pending_ops.json'
    path.write_text('{not valid json')
    q = PendingQueue.load(path)
    assert q.size() == 0


def test_load_version_mismatch_drops_file(tmp_path):
    path = tmp_path / 'pending_ops.json'
    path.write_text(json.dumps({'version': 99, 'ops': [{'bogus': 1}]}))
    q = PendingQueue.load(path)
    assert q.size() == 0


def test_load_missing_version_field_drops_file(tmp_path):
    path = tmp_path / 'pending_ops.json'
    path.write_text(json.dumps({'ops': []}))
    q = PendingQueue.load(path)
    assert q.size() == 0


def test_enqueue_creates_op_with_uuid_id(tmp_path):
    path = tmp_path / 'pending_ops.json'
    q = PendingQueue(path)
    op_id = q.enqueue(OP_ADD_FAVORITE, 9275, user_id=42)
    assert isinstance(op_id, str)
    assert len(op_id) > 10
    assert q.size() == 1


def test_enqueue_persists_to_disk(tmp_path):
    path = tmp_path / 'pending_ops.json'
    q = PendingQueue(path)
    q.enqueue(OP_ADD_FAVORITE, 9275, user_id=42)
    assert path.exists()
    raw = json.loads(path.read_text())
    assert raw['version'] == 1
    assert len(raw['ops']) == 1
    assert raw['ops'][0]['op'] == 'add_favorite'
    assert raw['ops'][0]['release_id'] == 9275
    assert raw['ops'][0]['user_id'] == 42


def test_enqueue_roundtrip_through_load(tmp_path):
    path = tmp_path / 'pending_ops.json'
    q1 = PendingQueue(path)
    q1.enqueue(OP_ADD_FAVORITE, 9275, user_id=42)
    q1.enqueue(
        OP_ADD_COLLECTION, 1000, user_id=42,
        payload={'collection_type': 'WATCHING'},
    )
    q1.enqueue(
        OP_SAVE_TIMECODE, 2000, user_id=42,
        payload={'episode_id': 'ep.0', 'time': 120.5, 'is_watched': False},
    )
    q2 = PendingQueue.load(path)
    assert q2.size() == 3


def test_enqueue_sets_defaults(tmp_path):
    path = tmp_path / 'pending_ops.json'
    q = PendingQueue(path)
    q.enqueue(OP_ADD_FAVORITE, 9275, user_id=42)
    raw = json.loads(path.read_text())
    op = raw['ops'][0]
    assert op['attempt_count'] == 0
    assert op['next_retry_at'] == 0.0
    assert op['last_error'] is None
    assert op['payload'] == {}
    assert op['created_at'] > 0


def test_peek_ready_returns_all_ops_when_next_retry_zero(tmp_path):
    path = tmp_path / 'pending_ops.json'
    q = PendingQueue(path)
    q.enqueue(OP_ADD_FAVORITE, 9275, user_id=42)
    q.enqueue(OP_ADD_FAVORITE, 9276, user_id=42)
    ready = q.peek_ready(now=1000.0)
    assert len(ready) == 2


def test_peek_ready_returns_ops_in_created_order(tmp_path):
    path = tmp_path / 'pending_ops.json'
    q = PendingQueue(path)
    q.enqueue(OP_ADD_FAVORITE, 9275, user_id=42)
    q.enqueue(OP_ADD_FAVORITE, 9276, user_id=42)
    q.enqueue(OP_ADD_FAVORITE, 9277, user_id=42)
    ready = q.peek_ready(now=10_000_000_000)
    assert [op.release_id for op in ready] == [9275, 9276, 9277]


def test_mark_success_removes_op(tmp_path):
    path = tmp_path / 'pending_ops.json'
    q = PendingQueue(path)
    op_id = q.enqueue(OP_ADD_FAVORITE, 9275, user_id=42)
    q.mark_success(op_id)
    assert q.size() == 0


def test_mark_success_persists(tmp_path):
    path = tmp_path / 'pending_ops.json'
    q = PendingQueue(path)
    op_id = q.enqueue(OP_ADD_FAVORITE, 9275, user_id=42)
    q.mark_success(op_id)
    q2 = PendingQueue.load(path)
    assert q2.size() == 0


def test_mark_success_unknown_id_is_noop(tmp_path):
    path = tmp_path / 'pending_ops.json'
    q = PendingQueue(path)
    q.enqueue(OP_ADD_FAVORITE, 9275, user_id=42)
    q.mark_success('no-such-id')
    assert q.size() == 1


def test_mark_failure_first_attempt_schedules_10s(tmp_path, monkeypatch):
    path = tmp_path / 'pending_ops.json'
    q = PendingQueue(path)
    op_id = q.enqueue(OP_ADD_FAVORITE, 9275, user_id=42)
    monkeypatch.setattr(
        'kitsune.storage.pending_queue.time.time', lambda: 1000.0
    )
    q.mark_failure(op_id, 'timeout')
    ready_at_1005 = q.peek_ready(now=1005.0)
    ready_at_1010 = q.peek_ready(now=1010.0)
    assert ready_at_1005 == []
    assert len(ready_at_1010) == 1


def test_mark_failure_progression_matches_backoff_table(tmp_path, monkeypatch):
    path = tmp_path / 'pending_ops.json'
    q = PendingQueue(path)
    op_id = q.enqueue(OP_ADD_FAVORITE, 9275, user_id=42)
    monkeypatch.setattr(
        'kitsune.storage.pending_queue.time.time', lambda: 1000.0
    )
    expected = [10, 30, 60, 120, 300, 600]
    for step in expected:
        q.mark_failure(op_id, 'timeout')
        op = q._ops[0]
        assert op.next_retry_at == 1000.0 + step
        # Undo the next_retry bump for the next iteration — we want to exercise
        # attempt_count progression, not calendar time.
        op.next_retry_at = 0.0
    assert op.attempt_count == 6


def test_mark_failure_caps_at_600s(tmp_path, monkeypatch):
    path = tmp_path / 'pending_ops.json'
    q = PendingQueue(path)
    op_id = q.enqueue(OP_ADD_FAVORITE, 9275, user_id=42)
    monkeypatch.setattr(
        'kitsune.storage.pending_queue.time.time', lambda: 1000.0
    )
    for _ in range(10):
        q.mark_failure(op_id, 'timeout')
        q._ops[0].next_retry_at = 0.0
    q.mark_failure(op_id, 'timeout')
    assert q._ops[0].next_retry_at == 1000.0 + 600
    assert q._ops[0].attempt_count == 11


def test_mark_failure_stores_error_message(tmp_path):
    path = tmp_path / 'pending_ops.json'
    q = PendingQueue(path)
    op_id = q.enqueue(OP_ADD_FAVORITE, 9275, user_id=42)
    q.mark_failure(op_id, 'connection refused')
    assert q._ops[0].last_error == 'connection refused'


def test_mark_failure_truncates_long_error(tmp_path):
    path = tmp_path / 'pending_ops.json'
    q = PendingQueue(path)
    op_id = q.enqueue(OP_ADD_FAVORITE, 9275, user_id=42)
    long_msg = 'x' * 500
    q.mark_failure(op_id, long_msg)
    assert len(q._ops[0].last_error) == 200


def test_mark_failure_persists(tmp_path):
    path = tmp_path / 'pending_ops.json'
    q = PendingQueue(path)
    op_id = q.enqueue(OP_ADD_FAVORITE, 9275, user_id=42)
    q.mark_failure(op_id, 'net error')
    q2 = PendingQueue.load(path)
    assert q2.size() == 1
    assert q2._ops[0].last_error == 'net error'
    assert q2._ops[0].attempt_count == 1


def test_mark_failure_unknown_id_is_noop(tmp_path):
    path = tmp_path / 'pending_ops.json'
    q = PendingQueue(path)
    q.enqueue(OP_ADD_FAVORITE, 9275, user_id=42)
    q.mark_failure('no-such-id', 'wat')
    assert q._ops[0].attempt_count == 0
