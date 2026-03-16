# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from kitsune import SITE_URL
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


def _safe_url(path: str | None) -> str | None:
    if not path or not isinstance(path, str):
        return None
    if not path.startswith('/') or path.startswith('//'):
        return None
    return SITE_URL + path


def _extract_poster_preview(poster_data: dict | None) -> str | None:
    if not poster_data:
        return None
    optimized = poster_data.get('optimized')
    if optimized and optimized.get('preview'):
        return _safe_url(optimized['preview'])
    preview = poster_data.get('preview')
    if preview:
        return _safe_url(preview)
    return None


def _extract_colors(poster_preview_url: str | None) -> list[list[int]] | None:
    if not poster_preview_url:
        return None
    try:
        from kitsune.ui.image_cache import get_from_memory
        texture = get_from_memory(poster_preview_url)
        if texture is None:
            return None
        from kitsune.ui.color_extractor import extract_colors
        colors = extract_colors(texture)
        return [list(c) for c in colors]
    except Exception:
        return None


def index_release(release_id: int, data: dict):
    idx = load()
    name_data = data.get('name', {})
    type_data = data.get('type', {})
    poster_preview = _extract_poster_preview(data.get('poster'))

    entry = {
        'main': name_data.get('main', '') if isinstance(name_data, dict) else str(name_data),
        'english': name_data.get('english') if isinstance(name_data, dict) else None,
        'alternative': name_data.get('alternative') if isinstance(name_data, dict) else None,
        'description': data.get('description'),
        'poster_preview': poster_preview,
        'type': type_data.get('value', '') if isinstance(type_data, dict) else str(type_data),
        'year': data.get('year', 0),
        'is_ongoing': data.get('is_ongoing', False),
        'genres': [g.get('id') for g in data.get('genres', []) if isinstance(g, dict)],
        'cached_at': int(time.time()),
    }

    colors = _extract_colors(poster_preview)
    if colors:
        entry['colors'] = colors

    idx['releases'][str(release_id)] = entry
    _save()


def remove_release(release_id: int):
    idx = load()
    idx['releases'].pop(str(release_id), None)
    _save()


def get_release_meta(release_id: int) -> dict | None:
    idx = load()
    return idx['releases'].get(str(release_id))
