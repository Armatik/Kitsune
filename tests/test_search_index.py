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
