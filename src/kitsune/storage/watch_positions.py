# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import os
from pathlib import Path

from kitsune.storage import _atomic_write_json

_POSITIONS_FILE = Path(
    os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
) / 'kitsune' / 'watch_positions.json'


def _load() -> dict:
    try:
        return json.loads(_POSITIONS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict):
    _atomic_write_json(_POSITIONS_FILE, data)


def get_position(release_id: int, ordinal: float) -> float:
    data = _load()
    return data.get(f'{release_id}_{ordinal}', 0)


def save_position(release_id: int, ordinal: float, position: float):
    data = _load()
    key = f'{release_id}_{ordinal}'
    if position > 5:
        data[key] = round(position, 1)
    elif key in data:
        del data[key]
    _save(data)


def mark_completed(release_id: int, ordinal: float):
    """Mark episode as fully watched (stores -1 as position)."""
    data = _load()
    key = f'{release_id}_{ordinal}'
    data[key] = -1
    _save(data)


def remove_position(release_id: int, ordinal: float):
    data = _load()
    key = f'{release_id}_{ordinal}'
    if key in data:
        del data[key]
        _save(data)


def get_all_for_release(release_id: int) -> dict[float, float]:
    """Return {ordinal: position} for all episodes of a release.

    position > 0 means partially watched, -1 means completed.
    """
    data = _load()
    prefix = f'{release_id}_'
    result = {}
    for key, value in data.items():
        if key.startswith(prefix):
            try:
                ordinal = float(key[len(prefix):])
                result[ordinal] = value
            except (ValueError, TypeError):
                continue
    return result


def get_count() -> int:
    return len(_load())


def get_size() -> int:
    try:
        return _POSITIONS_FILE.stat().st_size
    except FileNotFoundError:
        return 0


def clear_all():
    if _POSITIONS_FILE.exists():
        _POSITIONS_FILE.unlink()


_WATCHED_FRACTION = 0.9  # 90% watched = completed


def is_completed(pos, duration):
    """True if episode is completed or watched >= 90%."""
    if pos == -1:
        return True
    if pos > 0 and duration and duration > 0 and pos >= duration * _WATCHED_FRACTION:
        return True
    return False
