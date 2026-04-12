# SPDX-License-Identifier: GPL-3.0-or-later

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from kitsune.storage.sync_manager import SyncManager, MergeStrategy
from kitsune.storage import tags_store


class FakeSyncClient:
    def __init__(self):
        self.server_favorites = [10, 20, 30]
        self.server_collections = [
            {'release_id': 10, 'type_of_collection': 'WATCHING'},
            {'release_id': 40, 'type_of_collection': 'WATCHED'},
        ]
        self.pushed_favorites = []
        self.removed_favorites = []
        self.pushed_collections = []
        self._get_token = lambda: 'test-token'

    def get_favorite_ids(self, callback=None):
        callback(self.server_favorites, None)

    def get_collection_ids(self, callback=None):
        callback(self.server_collections, None)

    def add_favorites(self, release_ids, callback=None):
        self.pushed_favorites.extend(release_ids)
        if callback:
            callback(None, None)

    def remove_favorites(self, release_ids, callback=None):
        self.removed_favorites.extend(release_ids)
        if callback:
            callback(None, None)

    def add_to_collection(self, release_id, collection_type, callback=None):
        self.pushed_collections.append((release_id, collection_type))
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


# --- Merge strategy tests ---

def test_merge_strategy_default(mock_tags):
    tags_store.add_release('favorites', 99)
    client = FakeSyncClient()
    sm = SyncManager(client)

    sm.initial_sync(lambda ok, err: None)

    local_favs = tags_store.get_release_ids_for_tag('favorites')
    assert 10 in local_favs  # from server
    assert 99 in local_favs  # kept local
    assert 99 in client.pushed_favorites  # pushed to server


def test_prefer_server(mock_tags):
    tags_store.add_release('favorites', 99)
    client = FakeSyncClient()
    sm = SyncManager(client)

    sm.initial_sync(lambda ok, err: None,
                    strategy=MergeStrategy.PREFER_SERVER)

    local_favs = tags_store.get_release_ids_for_tag('favorites')
    assert 10 in local_favs
    assert 99 not in local_favs  # local-only removed
    assert len(client.pushed_favorites) == 0  # nothing pushed


def test_prefer_local(mock_tags):
    tags_store.add_release('favorites', 99)
    client = FakeSyncClient()
    sm = SyncManager(client)

    sm.initial_sync(lambda ok, err: None,
                    strategy=MergeStrategy.PREFER_LOCAL)

    local_favs = tags_store.get_release_ids_for_tag('favorites')
    assert 99 in local_favs  # local kept
    assert 99 in client.pushed_favorites  # pushed to server
    # Server-only items removed from server
    assert set(client.removed_favorites) == {10, 20, 30}


def test_merge_collections(mock_tags):
    client = FakeSyncClient()
    sm = SyncManager(client)
    sm.initial_sync(lambda ok, err: None)

    assert 10 in tags_store.get_release_ids_for_tag('watching')
    assert 40 in tags_store.get_release_ids_for_tag('watched')


def test_sync_sets_last_sync_time(mock_tags):
    client = FakeSyncClient()
    sm = SyncManager(client)
    assert sm.get_last_sync_time() is None
    sm.initial_sync(lambda ok, err: None)
    assert sm.get_last_sync_time() is not None


# --- Write-through tests ---

def test_toggle_favorite_synced(mock_tags):
    client = FakeSyncClient()
    sm = SyncManager(client)

    result = sm.toggle_favorite_synced(42)
    assert result is True
    assert tags_store.is_favorited(42)
    assert 42 in client.pushed_favorites

    result = sm.toggle_favorite_synced(42)
    assert result is False
    assert not tags_store.is_favorited(42)
    assert 42 in client.removed_favorites


def test_add_to_collection_synced(mock_tags):
    client = FakeSyncClient()
    sm = SyncManager(client)

    sm.add_to_tag_synced('watching', 55)
    assert 55 in tags_store.get_release_ids_for_tag('watching')
    assert (55, 'WATCHING') in client.pushed_collections


# --- Server counts ---

def test_fetch_server_counts(mock_tags):
    client = FakeSyncClient()
    sm = SyncManager(client)

    results = []
    sm.fetch_server_counts(lambda counts, err: results.append(counts))

    assert results[0]['favorites'] == 3
    assert results[0]['collections']['watching'] == 1
    assert results[0]['collections']['watched'] == 1


# --- Syncing state ---

def test_syncing_flag(mock_tags):
    client = FakeSyncClient()
    sm = SyncManager(client)
    assert not sm.is_syncing
    # After sync completes (synchronous fake), flag is cleared
    sm.initial_sync(lambda ok, err: None)
    assert not sm.is_syncing


def test_sync_manager_exposes_pending_queue():
    client = FakeSyncClient()
    sm = SyncManager(client)
    # The queue attribute exists and starts empty; actual usage comes in Stage 2.
    assert hasattr(sm, '_queue')
    assert sm._queue.size() == 0
