# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import os
import secrets
import tempfile
from pathlib import Path

_TAGS_FILE = Path(
    os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
) / 'kitsune' / 'tags.json'

_DEFAULT_FAVORITES = {
    'id': 'favorites',
    'name': 'Избранное',
    'icon_type': 'emoji',
    'icon_value': '⭐',
    'builtin': True,
    'order': 0,
    'releases': [],
}

TAG_COLORS = (
    'blue', 'teal', 'green', 'yellow',
    'orange', 'red', 'pink', 'purple', 'slate',
)


def _load() -> dict:
    try:
        data = json.loads(_TAGS_FILE.read_text())
        if 'tags' in data:
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {'tags': [{**_DEFAULT_FAVORITES, 'releases': []}]}


def _save(data: dict):
    _TAGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=_TAGS_FILE.parent)
    try:
        os.write(fd, json.dumps(data, ensure_ascii=False).encode())
        os.close(fd)
        os.replace(tmp, _TAGS_FILE)
    except BaseException:
        os.close(fd)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _find_tag(data: dict, tag_id: str) -> dict | None:
    for tag in data['tags']:
        if tag['id'] == tag_id:
            return tag
    return None


def get_all_tags() -> list[dict]:
    return _load()['tags']


def create_tag(name: str, icon_type: str, icon_value: str) -> dict:
    data = _load()
    tag = {
        'id': secrets.token_hex(4),
        'name': name,
        'icon_type': icon_type,
        'icon_value': icon_value,
        'builtin': False,
        'order': len(data['tags']),
        'releases': [],
    }
    data['tags'].append(tag)
    _save(data)
    return tag


def delete_tag(tag_id: str):
    if tag_id == 'favorites':
        return
    data = _load()
    data['tags'] = [t for t in data['tags'] if t['id'] != tag_id]
    _save(data)


def update_tag(tag_id: str, **kwargs):
    data = _load()
    tag = _find_tag(data, tag_id)
    if not tag or tag['builtin']:
        return
    for key in ('name', 'icon_type', 'icon_value'):
        if key in kwargs:
            tag[key] = kwargs[key]
    _save(data)


def add_release(tag_id: str, release_id: int):
    data = _load()
    tag = _find_tag(data, tag_id)
    if tag and release_id not in tag['releases']:
        tag['releases'].append(release_id)
        _save(data)


def remove_release(tag_id: str, release_id: int):
    data = _load()
    tag = _find_tag(data, tag_id)
    if tag and release_id in tag['releases']:
        tag['releases'].remove(release_id)
        _save(data)


def get_tags_for_release(release_id: int) -> list[dict]:
    data = _load()
    return [t for t in data['tags'] if release_id in t['releases']]


def get_release_ids_for_tag(tag_id: str) -> list[int]:
    data = _load()
    tag = _find_tag(data, tag_id)
    return list(tag['releases']) if tag else []


def is_favorited(release_id: int) -> bool:
    data = _load()
    fav = _find_tag(data, 'favorites')
    return fav is not None and release_id in fav['releases']


def toggle_favorite(release_id: int) -> bool:
    """Toggle favorite status. Returns new state."""
    data = _load()
    fav = _find_tag(data, 'favorites')
    if not fav:
        return False
    if release_id in fav['releases']:
        fav['releases'].remove(release_id)
        _save(data)
        return False
    fav['releases'].append(release_id)
    _save(data)
    return True


def get_count() -> int:
    return len(_load()['tags'])


def get_size() -> int:
    try:
        return _TAGS_FILE.stat().st_size
    except FileNotFoundError:
        return 0


def clear_all():
    _save({'tags': [{**_DEFAULT_FAVORITES, 'releases': []}]})
