# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import copy
import json
import os
import secrets
from pathlib import Path

from kitsune.storage import _atomic_write_json

_TAGS_FILE = Path(
    os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
) / 'kitsune' / 'tags.json'

_BUILTIN_TAGS = [
    {
        'id': 'favorites',
        'name': 'Favorites',
        'icon_type': 'symbolic',
        'icon_value': 'starred-symbolic',
        'builtin': True,
        'order': 0,
        'releases': [],
        'color': '#f5c211',
    },
    {
        'id': 'watching',
        'name': 'Watching',
        'icon_type': 'symbolic',
        'icon_value': 'media-playback-start-symbolic',
        'builtin': True,
        'order': 1,
        'releases': [],
        'color': '#9141ac',
    },
    {
        'id': 'watched',
        'name': 'Watched',
        'icon_type': 'symbolic',
        'icon_value': 'object-select-symbolic',
        'builtin': True,
        'order': 2,
        'releases': [],
        'color': '#26a269',
    },
    {
        'id': 'planned',
        'name': 'Planned',
        'icon_type': 'symbolic',
        'icon_value': 'view-list-bullet-symbolic',
        'builtin': True,
        'order': 3,
        'releases': [],
        'color': '#3584e4',
    },
    {
        'id': 'postponed',
        'name': 'Postponed',
        'icon_type': 'symbolic',
        'icon_value': 'media-playback-pause-symbolic',
        'builtin': True,
        'order': 4,
        'releases': [],
        'color': '#e66100',
    },
    {
        'id': 'abandoned',
        'name': 'Abandoned',
        'icon_type': 'symbolic',
        'icon_value': 'net.armatik.Kitsune.cross-large-symbolic',
        'builtin': True,
        'order': 5,
        'releases': [],
        'color': '#e01b24',
    },
]

# Map collection API types to local tag IDs
COLLECTION_TYPE_MAP = {
    'WATCHING': 'watching',
    'WATCHED': 'watched',
    'PLANNED': 'planned',
    'POSTPONED': 'postponed',
    'ABANDONED': 'abandoned',
}

TAG_COLORS = (
    'blue', 'teal', 'green', 'yellow',
    'orange', 'red', 'pink', 'purple', 'slate',
)


def _load() -> dict:
    if _TAGS_FILE.exists():
        try:
            with open(_TAGS_FILE) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {'tags': []}
    else:
        data = {'tags': []}

    # Ensure all builtin tags exist (migration for existing installs)
    existing_ids = {t['id'] for t in data['tags']}
    for bt in _BUILTIN_TAGS:
        if bt['id'] not in existing_ids:
            data['tags'].insert(bt['order'], copy.deepcopy(bt))

    # Migrate built-in tags from the legacy emoji icon set to Adwaita
    # symbolic icons. Only touches built-ins; user-created tags keep
    # whatever icon they were saved with.
    builtin_by_id = {bt['id']: bt for bt in _BUILTIN_TAGS}
    for tag in data['tags']:
        if not tag.get('builtin'):
            continue
        latest = builtin_by_id.get(tag['id'])
        if not latest:
            continue
        if tag.get('icon_type') == 'emoji':
            tag['icon_type'] = latest['icon_type']
            tag['icon_value'] = latest['icon_value']

    return data


def _save(data: dict):
    _atomic_write_json(_TAGS_FILE, data, ensure_ascii=False)


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
    data = _load()
    tag = _find_tag(data, tag_id)
    if not tag or tag.get('builtin'):
        return
    data['tags'] = [t for t in data['tags'] if t['id'] != tag_id]
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
    _save({'tags': copy.deepcopy(_BUILTIN_TAGS)})
