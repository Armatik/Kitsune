# SPDX-License-Identifier: GPL-3.0-or-later

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from kitsune.storage.pending_queue import PendingQueue


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
