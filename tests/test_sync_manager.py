# SPDX-License-Identifier: GPL-3.0-or-later

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from unittest.mock import MagicMock, patch
from kitsune.storage.sync_manager import SyncManager
from kitsune.storage import tags_store


class FakeSyncClient:
    def __init__(self):
        self.server_favorites = [10, 20, 30]
        self.server_collections = [
            {'release_id': 10, 'type_of_collection': 'WATCHING'},
            {'release_id': 40, 'type_of_collection': 'WATCHED'},
        ]
        self.pushed_favorites = []
        self.pushed_collections = []

    def get_favorite_ids(self, callback=None):
        callback(self.server_favorites, None)

    def get_collection_ids(self, callback=None):
        callback(self.server_collections, None)

    def add_favorites(self, release_ids, callback=None):
        self.pushed_favorites.extend(release_ids)
        if callback:
            callback(None, None)

    def add_to_collection(self, release_id, collection_type, callback=None):
        self.pushed_collections.append((release_id, collection_type))
        if callback:
            callback(None, None)

    def remove_favorites(self, release_ids, callback=None):
        if callback:
            callback(None, None)

    def remove_from_collection(self, release_ids, callback=None):
        if callback:
            callback(None, None)

    def get_timecodes(self, since=None, callback=None):
        callback([], None)

    def save_timecodes(self, timecodes, callback=None):
        if callback:
            callback(None, None)


def test_initial_merge_server_priority(mock_tags):
    # Add local-only release to favorites
    tags_store.add_release('favorites', 99)

    client = FakeSyncClient()
    sm = SyncManager(client)

    results = []
    sm.initial_sync(lambda ok, err: results.append((ok, err)))

    # Server favorites (10, 20, 30) + local-only (99) = merged
    local_favs = tags_store.get_release_ids_for_tag('favorites')
    assert 10 in local_favs
    assert 20 in local_favs
    assert 30 in local_favs
    assert 99 in local_favs

    # Local-only (99) should be pushed to server
    assert 99 in client.pushed_favorites


def test_initial_merge_collections(mock_tags):
    client = FakeSyncClient()
    sm = SyncManager(client)
    sm.initial_sync(lambda ok, err: None)

    # Server collection: release 10 is WATCHING
    watching = tags_store.get_release_ids_for_tag('watching')
    assert 10 in watching

    # Server collection: release 40 is WATCHED
    watched = tags_store.get_release_ids_for_tag('watched')
    assert 40 in watched


def test_sync_sets_last_sync_time(mock_tags):
    client = FakeSyncClient()
    sm = SyncManager(client)
    assert sm.get_last_sync_time() is None
    sm.initial_sync(lambda ok, err: None)
    assert sm.get_last_sync_time() is not None
