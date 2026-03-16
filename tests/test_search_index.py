# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from kitsune.storage import search_index


def test_load_empty(mock_index):
    data = search_index.load()
    assert data['version'] == 1
    assert data['releases'] == {}
    assert data['genres'] == {}
    assert data['franchises'] == {}


def test_load_corrupt_file(mock_index):
    mock_index.write_text('not json')
    data = search_index.load()
    assert data['version'] == 1
    assert data['releases'] == {}


def test_load_wrong_version(mock_index):
    mock_index.write_text(json.dumps({'version': 999}))
    data = search_index.load()
    assert data['version'] == 1
    assert data['releases'] == {}


_SAMPLE_RAW = {
    'id': 42,
    'name': {'main': 'Наруто', 'english': 'Naruto', 'alternative': 'ナルト'},
    'description': 'Молодой ниндзя мечтает стать хокаге.',
    'poster': {
        'optimized': {'preview': '/storage/poster/preview.jpg'},
        'preview': '/storage/poster/fallback.jpg',
    },
    'type': {'value': 'TV', 'description': 'TV'},
    'year': 2002,
    'is_ongoing': False,
    'genres': [{'id': 1, 'name': 'Сёнен'}, {'id': 5, 'name': 'Экшен'}],
}


def test_index_release(mock_index):
    search_index.index_release(42, _SAMPLE_RAW)
    meta = search_index.get_release_meta(42)
    assert meta is not None
    assert meta['main'] == 'Наруто'
    assert meta['english'] == 'Naruto'
    assert meta['alternative'] == 'ナルト'
    assert meta['description'] == 'Молодой ниндзя мечтает стать хокаге.'
    assert meta['type'] == 'TV'
    assert meta['year'] == 2002
    assert meta['is_ongoing'] is False
    assert meta['genres'] == [1, 5]
    assert 'cached_at' in meta


def test_index_release_poster_preview(mock_index):
    search_index.index_release(42, _SAMPLE_RAW)
    meta = search_index.get_release_meta(42)
    assert meta['poster_preview'] is not None
    assert 'preview' in meta['poster_preview']


def test_index_release_persists_to_disk(mock_index):
    search_index.index_release(42, _SAMPLE_RAW)
    assert mock_index.exists()
    data = json.loads(mock_index.read_text())
    assert '42' in data['releases']


def test_get_release_meta_missing(mock_index):
    assert search_index.get_release_meta(999) is None


def test_remove_release(mock_index):
    search_index.index_release(42, _SAMPLE_RAW)
    search_index.remove_release(42)
    assert search_index.get_release_meta(42) is None


def test_index_release_overwrites(mock_index):
    search_index.index_release(42, _SAMPLE_RAW)
    updated = {**_SAMPLE_RAW, 'year': 2023}
    search_index.index_release(42, updated)
    meta = search_index.get_release_meta(42)
    assert meta['year'] == 2023
