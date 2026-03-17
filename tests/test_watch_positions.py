# SPDX-License-Identifier: GPL-3.0-or-later

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from kitsune import watch_positions as wp


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


def test_is_completed_minus_one():
    assert wp.is_completed(-1, 1440) is True


def test_is_completed_90_percent():
    # 1300 / 1440 = 90.3% → completed
    assert wp.is_completed(1300, 1440) is True


def test_is_completed_below_90_percent():
    # 1200 / 1440 = 83.3% → not completed
    assert wp.is_completed(1200, 1440) is False


def test_is_completed_zero():
    assert wp.is_completed(0, 1440) is False


def test_is_completed_no_duration():
    assert wp.is_completed(100, None) is False
    assert wp.is_completed(100, 0) is False


def test_is_completed_exact_90_percent():
    # pos = 1296, duration = 1440 → 1296 / 1440 = 0.9 exactly → completed
    assert wp.is_completed(1296, 1440) is True


def test_is_completed_short_episode():
    # 90s episode, 82s watched = 91% → completed
    assert wp.is_completed(82, 90) is True
    # 90s episode, 6s watched = 6.7% → not completed
    assert wp.is_completed(6, 90) is False


def test_is_completed_short_episode_minus_one():
    assert wp.is_completed(-1, 90) is True
