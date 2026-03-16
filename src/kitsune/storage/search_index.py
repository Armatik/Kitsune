# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from kitsune.storage import _atomic_write_json

_VERSION = 1
_GENRES_TTL = 604_800    # 7 days
_FRANCHISES_TTL = 86_400  # 24 hours

_INDEX_FILE = Path(
    os.environ.get('XDG_CACHE_HOME', os.path.expanduser('~/.cache'))
) / 'kitsune' / 'index.json'

_cache: dict | None = None


def _empty() -> dict:
    return {'version': _VERSION, 'releases': {}, 'genres': {}, 'franchises': {}}


def load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    try:
        data = json.loads(_INDEX_FILE.read_text())
        if not isinstance(data, dict) or data.get('version') != _VERSION:
            _cache = _empty()
            return _cache
        _cache = data
        return _cache
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        _cache = _empty()
        return _cache


def _save():
    if _cache is not None:
        _atomic_write_json(_INDEX_FILE, _cache, ensure_ascii=False)
