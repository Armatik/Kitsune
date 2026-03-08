# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import os
from pathlib import Path

_POSITIONS_FILE = Path(
    os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
) / 'kitsune' / 'watch_positions.json'


def _load() -> dict:
    try:
        return json.loads(_POSITIONS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict):
    _POSITIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _POSITIONS_FILE.write_text(json.dumps(data))


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


def remove_position(release_id: int, ordinal: float):
    data = _load()
    key = f'{release_id}_{ordinal}'
    if key in data:
        del data[key]
        _save(data)


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
