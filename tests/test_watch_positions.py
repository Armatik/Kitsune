# SPDX-License-Identifier: GPL-3.0-or-later

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import kitsune.watch_positions as wp


def _setup_tmp(monkeypatch, tmp_path):
    f = tmp_path / 'watch_positions.json'
    monkeypatch.setattr(wp, '_POSITIONS_FILE', f)
    return f


def test_mark_completed(monkeypatch, tmp_path):
    _setup_tmp(monkeypatch, tmp_path)
    wp.save_position(1, 1.0, 120.0)
    wp.mark_completed(1, 1.0)
    assert wp.get_position(1, 1.0) == -1


def test_mark_completed_creates_entry(monkeypatch, tmp_path):
    _setup_tmp(monkeypatch, tmp_path)
    wp.mark_completed(1, 2.0)
    assert wp.get_position(1, 2.0) == -1


def test_get_all_for_release(monkeypatch, tmp_path):
    _setup_tmp(monkeypatch, tmp_path)
    wp.save_position(1, 1.0, 60.0)
    wp.save_position(1, 2.0, 120.0)
    wp.mark_completed(1, 3.0)
    wp.save_position(2, 1.0, 30.0)  # different release

    result = wp.get_all_for_release(1)
    assert result == {1.0: 60.0, 2.0: 120.0, 3.0: -1}


def test_get_all_for_release_empty(monkeypatch, tmp_path):
    _setup_tmp(monkeypatch, tmp_path)
    result = wp.get_all_for_release(99)
    assert result == {}
