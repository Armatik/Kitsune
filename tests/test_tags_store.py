# SPDX-License-Identifier: GPL-3.0-or-later

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import kitsune.tags_store as tags_store


def _use_temp_file(tmp_path):
    """Redirect storage to a temp file for testing."""
    f = tmp_path / 'tags.json'
    tags_store._TAGS_FILE = f
    return f


def test_initial_state_has_favorites(tmp_path):
    _use_temp_file(tmp_path)
    tags = tags_store.get_all_tags()
    assert len(tags) == 1
    assert tags[0]['id'] == 'favorites'
    assert tags[0]['builtin'] is True


def test_create_emoji_tag(tmp_path):
    _use_temp_file(tmp_path)
    tag = tags_store.create_tag('Топ сезона', 'emoji', '🔥')
    assert tag['name'] == 'Топ сезона'
    assert tag['icon_type'] == 'emoji'
    assert tag['icon_value'] == '🔥'
    assert tag['builtin'] is False
    assert len(tag['id']) == 8


def test_create_color_tag(tmp_path):
    _use_temp_file(tmp_path)
    tag = tags_store.create_tag('Романтика', 'color', 'pink')
    assert tag['icon_type'] == 'color'
    assert tag['icon_value'] == 'pink'


def test_delete_custom_tag(tmp_path):
    _use_temp_file(tmp_path)
    tag = tags_store.create_tag('Temp', 'emoji', '💎')
    tags_store.delete_tag(tag['id'])
    ids = [t['id'] for t in tags_store.get_all_tags()]
    assert tag['id'] not in ids


def test_cannot_delete_favorites(tmp_path):
    _use_temp_file(tmp_path)
    tags_store.delete_tag('favorites')
    assert any(t['id'] == 'favorites' for t in tags_store.get_all_tags())


def test_add_release_to_tag(tmp_path):
    _use_temp_file(tmp_path)
    tags_store.add_release('favorites', 42)
    tags = tags_store.get_all_tags()
    fav = [t for t in tags if t['id'] == 'favorites'][0]
    assert 42 in fav['releases']


def test_remove_release_from_tag(tmp_path):
    _use_temp_file(tmp_path)
    tags_store.add_release('favorites', 42)
    tags_store.remove_release('favorites', 42)
    tags = tags_store.get_all_tags()
    fav = [t for t in tags if t['id'] == 'favorites'][0]
    assert 42 not in fav['releases']


def test_get_tags_for_release(tmp_path):
    _use_temp_file(tmp_path)
    tag = tags_store.create_tag('Test', 'color', 'blue')
    tags_store.add_release('favorites', 100)
    tags_store.add_release(tag['id'], 100)
    result = tags_store.get_tags_for_release(100)
    assert len(result) == 2
    ids = [t['id'] for t in result]
    assert 'favorites' in ids
    assert tag['id'] in ids


def test_get_tags_for_release_empty(tmp_path):
    _use_temp_file(tmp_path)
    result = tags_store.get_tags_for_release(999)
    assert result == []


def test_is_favorited(tmp_path):
    _use_temp_file(tmp_path)
    assert tags_store.is_favorited(42) is False
    tags_store.add_release('favorites', 42)
    assert tags_store.is_favorited(42) is True


def test_toggle_favorite(tmp_path):
    _use_temp_file(tmp_path)
    tags_store.toggle_favorite(42)
    assert tags_store.is_favorited(42) is True
    tags_store.toggle_favorite(42)
    assert tags_store.is_favorited(42) is False


def test_get_release_ids_for_tag(tmp_path):
    _use_temp_file(tmp_path)
    tags_store.add_release('favorites', 1)
    tags_store.add_release('favorites', 2)
    ids = tags_store.get_release_ids_for_tag('favorites')
    assert set(ids) == {1, 2}


def test_update_tag(tmp_path):
    _use_temp_file(tmp_path)
    tag = tags_store.create_tag('Old', 'emoji', '💎')
    tags_store.update_tag(tag['id'], name='New', icon_type='color', icon_value='red')
    updated = [t for t in tags_store.get_all_tags() if t['id'] == tag['id']][0]
    assert updated['name'] == 'New'
    assert updated['icon_type'] == 'color'
    assert updated['icon_value'] == 'red'


def test_stats(tmp_path):
    _use_temp_file(tmp_path)
    assert tags_store.get_count() == 1
    tags_store.create_tag('A', 'emoji', '🎯')
    assert tags_store.get_count() == 2


def test_clear_all(tmp_path):
    _use_temp_file(tmp_path)
    tags_store.create_tag('A', 'emoji', '🎯')
    tags_store.add_release('favorites', 42)
    tags_store.clear_all()
    tags = tags_store.get_all_tags()
    assert len(tags) == 1
    assert tags[0]['releases'] == []
