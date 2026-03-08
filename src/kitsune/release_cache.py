# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import os
from pathlib import Path

_CACHE_DIR = Path(
    os.environ.get('XDG_CACHE_HOME', os.path.expanduser('~/.cache'))
) / 'kitsune' / 'releases'


def get(release_id: int) -> dict | None:
    path = _CACHE_DIR / f'{release_id}.json'
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save(release_id: int, data: dict):
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (_CACHE_DIR / f'{release_id}.json').write_text(json.dumps(data))


def get_count() -> int:
    if not _CACHE_DIR.exists():
        return 0
    return sum(1 for f in _CACHE_DIR.iterdir() if f.suffix == '.json')


def get_size() -> int:
    if not _CACHE_DIR.exists():
        return 0
    return sum(f.stat().st_size for f in _CACHE_DIR.iterdir() if f.suffix == '.json')


def clear_all():
    if _CACHE_DIR.exists():
        for f in _CACHE_DIR.iterdir():
            if f.suffix == '.json':
                f.unlink()
