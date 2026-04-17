# SPDX-License-Identifier: GPL-3.0-or-later

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from kitsune.storage.sync_manager import SyncManager, MergeStrategy
from kitsune.storage import tags_store

sys.path.insert(0, os.path.dirname(__file__))

from fakes.fake_api_client import FakeApiClient
from kitsune.storage.pending_queue import (
    PendingQueue, OP_ADD_FAVORITE, OP_REMOVE_FAVORITE,
    OP_ADD_COLLECTION, OP_REMOVE_COLLECTION,
)


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


# --- Pub/sub and accessor tests (Stage 2) ---

def test_connect_sync_error_fires_on_emit():
    client = FakeSyncClient()
    sm = SyncManager(client)
    received = []
    sm.connect_sync_error(lambda op, rid, err: received.append((op, rid, err)))
    sm._emit_sync_error('add_favorite', 9275, 'timeout')
    assert received == [('add_favorite', 9275, 'timeout')]


def test_connect_queue_changed_fires_on_emit():
    client = FakeSyncClient()
    sm = SyncManager(client)
    received = []
    sm.connect_queue_changed(lambda size: received.append(size))
    sm._emit_queue_changed()
    assert received == [0]


def test_connect_sync_complete_fires_on_emit():
    client = FakeSyncClient()
    sm = SyncManager(client)
    received = []
    sm.connect_sync_complete(lambda ok: received.append(ok))
    sm._emit_sync_complete(True)
    assert received == [True]


def test_set_user_id():
    client = FakeSyncClient()
    sm = SyncManager(client)
    assert sm._user_id == 0
    sm.set_user_id(42)
    assert sm._user_id == 42


def test_queue_size_delegates():
    client = FakeSyncClient()
    sm = SyncManager(client)
    assert sm.queue_size() == 0


def test_queue_has_errors_delegates():
    client = FakeSyncClient()
    sm = SyncManager(client)
    assert sm.queue_has_errors() is False


def test_last_queue_error_delegates():
    client = FakeSyncClient()
    sm = SyncManager(client)
    assert sm.last_queue_error() is None


# --- Drain tests (Stage 2) ---

def _make_sm_with_fake(tmp_path):
    """Helper: SyncManager with FakeApiClient and tmp queue."""
    client = FakeApiClient()
    sm = SyncManager(client)
    # Redirect queue to tmp to avoid touching real user dir
    sm._queue = PendingQueue(tmp_path / 'pending_ops.json')
    sm.set_user_id(42)
    return sm, client


def test_drain_dispatches_add_favorite(tmp_path, mock_tags):
    sm, client = _make_sm_with_fake(tmp_path)
    sm._queue.enqueue(OP_ADD_FAVORITE, 9275, user_id=42)
    sm._drain_queue()
    assert client.call_log == [('add_favorites', [9275])]
    client.flush_all()
    assert sm._queue.size() == 0


def test_drain_dispatches_remove_favorite(tmp_path, mock_tags):
    sm, client = _make_sm_with_fake(tmp_path)
    sm._queue.enqueue(OP_REMOVE_FAVORITE, 9275, user_id=42)
    sm._drain_queue()
    assert client.call_log == [('remove_favorites', [9275])]
    client.flush_all()
    assert sm._queue.size() == 0


def test_drain_dispatches_add_collection(tmp_path, mock_tags):
    sm, client = _make_sm_with_fake(tmp_path)
    sm._queue.enqueue(
        OP_ADD_COLLECTION, 9275, user_id=42,
        payload={'collection_type': 'WATCHING'},
    )
    sm._drain_queue()
    assert client.call_log == [('add_to_collection', 9275, 'WATCHING')]
    client.flush_all()
    assert sm._queue.size() == 0


def test_drain_dispatches_remove_collection(tmp_path, mock_tags):
    sm, client = _make_sm_with_fake(tmp_path)
    sm._queue.enqueue(OP_REMOVE_COLLECTION, 9275, user_id=42)
    sm._drain_queue()
    assert client.call_log == [('remove_from_collection', [9275])]
    client.flush_all()
    assert sm._queue.size() == 0


def test_drain_emits_queue_changed_on_success(tmp_path, mock_tags):
    sm, client = _make_sm_with_fake(tmp_path)
    sm._queue.enqueue(OP_ADD_FAVORITE, 9275, user_id=42)
    sizes = []
    sm.connect_queue_changed(lambda s: sizes.append(s))
    sm._drain_queue()
    client.flush_all()
    assert 0 in sizes


def test_drain_emits_sync_error_on_failure(tmp_path, mock_tags):
    sm, client = _make_sm_with_fake(tmp_path)
    sm._queue.enqueue(OP_ADD_FAVORITE, 9275, user_id=42)
    errors = []
    sm.connect_sync_error(lambda op, rid, err: errors.append((op, rid, err)))
    sm._drain_queue()
    client.fail_next('server 500')
    assert len(errors) == 1
    assert errors[0] == ('add_favorite', 9275, 'server 500')
    assert sm._queue.size() == 1  # op still in queue for retry


def test_drain_reentrancy_guard(tmp_path, mock_tags):
    sm, client = _make_sm_with_fake(tmp_path)
    sm._queue.enqueue(OP_ADD_FAVORITE, 9275, user_id=42)
    sm._draining = True  # simulate already draining
    sm._drain_queue()
    assert client.call_log == []  # nothing dispatched


def test_drain_chains_multiple_ops(tmp_path, mock_tags):
    sm, client = _make_sm_with_fake(tmp_path)
    sm._queue.enqueue(OP_ADD_FAVORITE, 9275, user_id=42)
    sm._queue.enqueue(OP_ADD_FAVORITE, 9276, user_id=42)
    sm._drain_queue()
    # First op dispatched
    assert len(client.call_log) == 1
    client.flush_next()  # first succeeds → second dispatched
    assert len(client.call_log) == 2
    client.flush_next()  # second succeeds
    assert sm._queue.size() == 0


# --- Write-through tests (updated for queue routing) ---

def test_toggle_favorite_synced_enqueues_and_drains(mock_tags, tmp_path):
    sm, client = _make_sm_with_fake(tmp_path)

    result = sm.toggle_favorite_synced(42)
    assert result is True
    assert tags_store.is_favorited(42)
    # Op is in queue, not dispatched yet (idle-scheduled)
    assert sm._queue.size() == 1
    assert client.call_log == []
    # Drain and flush to simulate real async cycle
    sm._drain_queue()
    client.flush_all()
    assert ('add_favorites', [42]) in client.call_log
    assert sm._queue.size() == 0

    result = sm.toggle_favorite_synced(42)
    assert result is False
    assert not tags_store.is_favorited(42)
    sm._drain_queue()
    client.flush_all()
    assert ('remove_favorites', [42]) in client.call_log


def test_add_to_collection_synced_enqueues(mock_tags, tmp_path):
    sm, client = _make_sm_with_fake(tmp_path)

    sm.add_to_tag_synced('watching', 55)
    assert 55 in tags_store.get_release_ids_for_tag('watching')
    assert sm._queue.size() == 1
    sm._drain_queue()
    client.flush_all()
    assert ('add_to_collection', 55, 'WATCHING') in client.call_log


def test_remove_from_tag_synced_enqueues(mock_tags, tmp_path):
    sm, client = _make_sm_with_fake(tmp_path)
    tags_store.add_release('watching', 55)

    sm.remove_from_tag_synced('watching', 55)
    assert 55 not in tags_store.get_release_ids_for_tag('watching')
    assert sm._queue.size() == 1
    sm._drain_queue()
    client.flush_all()
    assert ('remove_from_collection', [55]) in client.call_log


def test_write_through_schedules_drain(mock_tags, tmp_path, monkeypatch):
    """Verify that write-through calls GLib.idle_add to schedule drain."""
    sm, client = _make_sm_with_fake(tmp_path)
    scheduled = []
    monkeypatch.setattr(
        'kitsune.storage.sync_manager.GLib.idle_add',
        lambda fn: scheduled.append(fn),
    )
    sm.add_to_tag_synced('favorites', 9275)
    assert len(scheduled) == 1  # _schedule_drain called once


def test_write_through_not_logged_in_skips_enqueue(mock_tags, tmp_path):
    """If not logged in, local change happens but no enqueue."""
    sm, client = _make_sm_with_fake(tmp_path)
    sm._client._get_token = lambda: None  # simulate not logged in
    sm.add_to_tag_synced('favorites', 9275)
    assert tags_store.is_favorited(9275)  # local still applies
    assert sm._queue.size() == 0  # not enqueued


def test_write_through_does_not_double_schedule(mock_tags, tmp_path, monkeypatch):
    """Two write-throughs before the idle fires only schedule one drain."""
    sm, client = _make_sm_with_fake(tmp_path)
    scheduled = []
    monkeypatch.setattr(
        'kitsune.storage.sync_manager.GLib.idle_add',
        lambda fn: scheduled.append(fn),
    )
    sm.add_to_tag_synced('favorites', 9275)
    sm.add_to_tag_synced('favorites', 9276)
    assert len(scheduled) == 1  # second write-through suppresses double schedule


def test_write_through_custom_tag_skips_enqueue(mock_tags, tmp_path):
    """Custom (non-synced) tags apply locally but are not enqueued."""
    sm, client = _make_sm_with_fake(tmp_path)
    tags_store.create_tag('Custom Test', 'emoji', '🔥')
    custom_id = [t['id'] for t in tags_store.get_all_tags()
                 if not t.get('builtin')][0]
    sm.add_to_tag_synced(custom_id, 9275)
    assert 9275 in tags_store.get_release_ids_for_tag(custom_id)
    assert sm._queue.size() == 0  # custom tag not enqueued
