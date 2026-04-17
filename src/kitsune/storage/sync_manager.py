# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import time

from gi.repository import GLib

from kitsune.storage import tags_store, watch_positions
from kitsune.storage.pending_queue import (
    PendingQueue, OP_ADD_FAVORITE, OP_REMOVE_FAVORITE,
    OP_ADD_COLLECTION, OP_REMOVE_COLLECTION,
)

log = logging.getLogger('kitsune.sync')

COLLECTION_MAP = {
    'WATCHING': 'watching',
    'WATCHED': 'watched',
    'PLANNED': 'planned',
    'POSTPONED': 'postponed',
    'ABANDONED': 'abandoned',
}

_TAG_TO_COLLECTION = {v: k for k, v in COLLECTION_MAP.items()}

# All builtin tag IDs that sync with the server
SYNCED_TAGS = {'favorites'} | set(COLLECTION_MAP.values())


class MergeStrategy:
    MERGE = 'merge'          # bidirectional, server wins conflicts
    PREFER_LOCAL = 'local'   # push local → server
    PREFER_SERVER = 'server' # pull server → local


def _noop(data, error):
    pass


class SyncManager:
    def __init__(self, client):
        self._client = client
        self._last_sync = None
        self._syncing = False
        self._queue = PendingQueue.load()
        self._user_id = 0
        self._draining = False
        self._drain_scheduled = False
        self._retry_timer_id = None
        # Pub/sub callback lists (matching SessionManager pattern)
        self._on_sync_error_cbs = []
        self._on_queue_changed_cbs = []
        self._on_sync_complete_cbs = []

    @property
    def is_syncing(self):
        return self._syncing

    def get_last_sync_time(self):
        return self._last_sync

    def is_logged_in(self):
        return bool(self._client and
                     hasattr(self._client, '_get_token') and
                     self._client._get_token and
                     self._client._get_token())

    # --- Pub/sub (callback-list pattern, see SessionManager) ---

    def connect_sync_error(self, callback):
        """callback(op_kind: str, release_id: int, error: str)"""
        self._on_sync_error_cbs.append(callback)

    def connect_queue_changed(self, callback):
        """callback(size: int)"""
        self._on_queue_changed_cbs.append(callback)

    def connect_sync_complete(self, callback):
        """callback(success: bool)"""
        self._on_sync_complete_cbs.append(callback)

    def _emit_sync_error(self, op_kind, release_id, error):
        for cb in self._on_sync_error_cbs:
            cb(op_kind, release_id, error)

    def _emit_queue_changed(self):
        size = self._queue.size()
        for cb in self._on_queue_changed_cbs:
            cb(size)

    def _emit_sync_complete(self, success):
        for cb in self._on_sync_complete_cbs:
            cb(success)

    # --- Public queue accessors (for profile UI) ---

    def set_user_id(self, user_id):
        self._user_id = user_id

    def queue_size(self):
        return self._queue.size()

    def queue_has_errors(self):
        return self._queue.has_errors()

    def last_queue_error(self):
        return self._queue.last_error()

    # --- Drain queue (Stage 2) ---

    _OP_DISPATCH = {
        OP_ADD_FAVORITE: '_dispatch_add_favorite',
        OP_REMOVE_FAVORITE: '_dispatch_remove_favorite',
        OP_ADD_COLLECTION: '_dispatch_add_collection',
        OP_REMOVE_COLLECTION: '_dispatch_remove_collection',
    }

    def _drain_queue(self):
        """Process ready ops from the queue. Reentrancy-guarded."""
        if self._draining:
            return
        self._draining = True
        self._drain_scheduled = False
        self._drain_next()

    def _drain_next(self):
        """Dispatch the next ready op, or finish draining.

        Unknown op kinds (added by a newer version and loaded from disk on
        an older binary) are skipped but NOT removed — the op stays in the
        queue until a version that understands it runs and drains. This
        prevents silent data loss during downgrades.
        """
        ready = self._queue.peek_ready(time.time())
        # Find the first op with a known kind; skip unknowns
        op = None
        dispatch_method = None
        for candidate in ready:
            method = self._OP_DISPATCH.get(candidate.op)
            if method:
                op = candidate
                dispatch_method = method
                break
            log.debug(
                'Skipping unknown op kind %r in queue (op id %s) — '
                'leaving in place for a future version', candidate.op, candidate.id)
        if op is None:
            self._draining = False
            return
        self._queue.mark_in_flight(op.id)
        getattr(self, dispatch_method)(op)

    def _dispatch_add_favorite(self, op):
        self._client.add_favorites(
            [op.release_id],
            lambda data, err: self._on_op_result(op, err))

    def _dispatch_remove_favorite(self, op):
        self._client.remove_favorites(
            [op.release_id],
            lambda data, err: self._on_op_result(op, err))

    def _dispatch_add_collection(self, op):
        self._client.add_to_collection(
            op.release_id,
            op.payload.get('collection_type', ''),
            lambda data, err: self._on_op_result(op, err))

    def _dispatch_remove_collection(self, op):
        self._client.remove_from_collection(
            [op.release_id],
            lambda data, err: self._on_op_result(op, err))

    def _on_op_result(self, op, error):
        """Handle the result of a dispatched op.

        Success is detected by `error is None` — not by inspecting `data`,
        which may legitimately be None for successful drain operations.

        Wrapped in try/except so that an exception from `_save()` (disk full,
        permission error) or a subscriber callback does not permanently
        deadlock the drain pipeline by leaving `_draining = True`. On any
        exception, we log, clear the guard, and re-schedule a drain — the
        next idle tick will retry from a clean state.
        """
        try:
            if error:
                self._queue.mark_failure(op.id, str(error))
                self._emit_sync_error(op.op, op.release_id, str(error))
                self._emit_queue_changed()
            else:
                self._queue.mark_success(op.id)
                self._emit_queue_changed()
            self._drain_next()
        except Exception:
            log.exception('Drain result handler raised; resetting drain state')
            self._draining = False
            self._schedule_drain()

    def _schedule_drain(self):
        """Schedule a drain on the next GLib idle tick.

        Uses a flag to avoid scheduling multiple drains in the same idle
        cycle. The flag is cleared at the start of _drain_queue, so a new
        drain can be scheduled while the current one is running.
        """
        if self._drain_scheduled:
            return
        self._drain_scheduled = True
        GLib.idle_add(self._drain_queue)
        self._start_retry_timer()

    def _start_retry_timer(self):
        """Start the 10-second retry timer (idempotent)."""
        if self._retry_timer_id is not None:
            return
        self._retry_timer_id = GLib.timeout_add_seconds(
            10, self._retry_tick)

    def _stop_retry_timer(self):
        """Stop the retry timer."""
        if self._retry_timer_id is not None:
            GLib.source_remove(self._retry_timer_id)
            self._retry_timer_id = None

    def _retry_tick(self):
        """Called every 10s: if there are ready ops, schedule a drain.

        Returns True (GLib.SOURCE_CONTINUE) to keep the timer alive.
        """
        ready = self._queue.peek_ready(time.time())
        if ready:
            self._schedule_drain()
        return True

    def force_drain(self):
        """Reset all retry timers and drain immediately.

        Used by the 'Retry now' button in the profile UI (Stage 7).
        Attempt counts and last_error values are preserved — this is a
        user-initiated wake-up, not a state reset.
        """
        self._queue.reset_all_retries()
        self._drain_queue()

    # --- Initial sync with strategy ---

    def initial_sync(self, callback=None, strategy=MergeStrategy.MERGE):
        """Full sync with chosen merge strategy."""
        if self._syncing:
            log.debug('Sync already in progress, skipping')
            if callback:
                callback(False, 'already_syncing')
            return
        self._syncing = True
        log.debug('Starting sync with strategy: %s', strategy)
        self._strategy = strategy
        self._sync_favorites(
            lambda: self._sync_collections(
                lambda: self._sync_done(callback)))

    def sync_now(self, callback=None):
        """Manual sync — always merge."""
        self.initial_sync(callback, MergeStrategy.MERGE)

    def pull_from_server(self, callback=None):
        """Quiet pull — server wins, no push."""
        self.initial_sync(callback, MergeStrategy.PREFER_SERVER)

    # --- Write-through (real-time sync on user action) ---

    def add_to_tag_synced(self, tag_id, release_id):
        """Add release to tag locally + enqueue server push."""
        tags_store.add_release(tag_id, release_id)
        if not self.is_logged_in():
            return
        if tag_id == 'favorites':
            self._queue.enqueue(
                OP_ADD_FAVORITE, release_id, user_id=self._user_id)
        elif tag_id in _TAG_TO_COLLECTION:
            self._queue.enqueue(
                OP_ADD_COLLECTION, release_id, user_id=self._user_id,
                payload={'collection_type': _TAG_TO_COLLECTION[tag_id]})
        else:
            return  # custom tag, no server sync
        self._emit_queue_changed()
        self._schedule_drain()

    def remove_from_tag_synced(self, tag_id, release_id):
        """Remove release from tag locally + enqueue server push."""
        tags_store.remove_release(tag_id, release_id)
        if not self.is_logged_in():
            return
        if tag_id == 'favorites':
            self._queue.enqueue(
                OP_REMOVE_FAVORITE, release_id, user_id=self._user_id)
        elif tag_id in _TAG_TO_COLLECTION:
            self._queue.enqueue(
                OP_REMOVE_COLLECTION, release_id, user_id=self._user_id)
        else:
            return
        self._emit_queue_changed()
        self._schedule_drain()

    def toggle_favorite_synced(self, release_id):
        """Toggle favorite locally + enqueue server push. Returns new state."""
        is_fav = tags_store.is_favorited(release_id)
        if is_fav:
            self.remove_from_tag_synced('favorites', release_id)
        else:
            self.add_to_tag_synced('favorites', release_id)
        return not is_fav

    # --- Watch positions ---

    def flush_timecodes(self, release_id=None, callback=None):
        """Push local watch positions to server.

        Called on player exit and app close.
        If release_id given, only flush that release.
        """
        if not self.is_logged_in():
            if callback:
                callback(True, None)
            return

        if release_id:
            positions = watch_positions.get_all_for_release(release_id)
        else:
            positions = watch_positions._load()

        timecodes = []
        for key, pos in positions.items():
            if release_id:
                # key is ordinal (float), pos is position
                timecodes.append({
                    'time': pos if pos != -1 else 0,
                    'is_watched': pos == -1,
                })
            else:
                # key is 'releaseid_ordinal', pos is position
                timecodes.append({
                    'time': pos if pos != -1 else 0,
                    'is_watched': pos == -1,
                })

        if timecodes:
            log.debug('Flushing %d timecodes to server', len(timecodes))
            self._client.save_timecodes(timecodes, callback or _noop)
        elif callback:
            callback(True, None)

    def pull_timecodes(self, callback=None):
        """Pull watch positions from server into local store."""
        if not self.is_logged_in():
            if callback:
                callback(True, None)
            return

        def on_timecodes(data, error):
            if error or not data:
                log.debug('Timecodes pull failed: %s', error)
                if callback:
                    callback(False, error)
                return
            # Data is list of [episode_id, time, is_watched]
            log.debug('Pulled %d timecodes from server', len(data))
            if callback:
                callback(True, None)

        self._client.get_timecodes(callback=on_timecodes)

    # --- Server counts (for merge dialog) ---

    def fetch_server_counts(self, callback):
        """Fetch server favorite + collection counts for merge dialog."""
        counts = {'favorites': 0, 'collections': {}}

        def on_favs(data, error):
            if not error and data:
                counts['favorites'] = len(data)
            self._client.get_collection_ids(on_collections)

        def on_collections(data, error):
            if not error and data:
                for entry in data:
                    if isinstance(entry, dict):
                        ctype = entry.get('type_of_collection', '')
                        tag_id = COLLECTION_MAP.get(ctype)
                        if tag_id:
                            counts['collections'][tag_id] = \
                                counts['collections'].get(tag_id, 0) + 1
            callback(counts, None)

        self._client.get_favorite_ids(on_favs)

    # --- Internal sync logic ---

    def _sync_done(self, callback):
        self._syncing = False
        self._last_sync = time.time()
        log.debug('Sync complete')
        if callback:
            callback(True, None)

    def _sync_favorites(self, then):
        def on_server_favs(server_ids, error):
            if error:
                log.debug('Favorites sync failed: %s', error)
                then()
                return
            local_ids = set(tags_store.get_release_ids_for_tag('favorites'))
            server_set = set(server_ids) if server_ids else set()
            strategy = self._strategy

            if strategy == MergeStrategy.PREFER_SERVER:
                # Clear local, set to server
                for rid in local_ids - server_set:
                    tags_store.remove_release('favorites', rid)
                for rid in server_set - local_ids:
                    tags_store.add_release('favorites', rid)
                then()
            elif strategy == MergeStrategy.PREFER_LOCAL:
                # Push all local to server (add missing, remove extra)
                to_add = local_ids - server_set
                to_remove = server_set - local_ids
                if to_add:
                    self._client.add_favorites(list(to_add), _noop)
                if to_remove:
                    self._client.remove_favorites(list(to_remove), _noop)
                then()
            else:
                # MERGE: server wins conflicts, push local-only
                for rid in server_set - local_ids:
                    tags_store.add_release('favorites', rid)
                local_only = local_ids - server_set
                if local_only:
                    self._client.add_favorites(
                        list(local_only), lambda d, e: then())
                else:
                    then()

        self._client.get_favorite_ids(on_server_favs)

    def _sync_collections(self, then):
        def on_server_collections(server_entries, error):
            if error:
                log.debug('Collections sync failed: %s', error)
                then()
                return

            server_by_tag = {}
            for entry in (server_entries or []):
                rid = entry.get('release_id', 0) if isinstance(entry, dict) else 0
                ctype = entry.get('type_of_collection', '') if isinstance(entry, dict) else ''
                tag_id = COLLECTION_MAP.get(ctype)
                if tag_id and rid:
                    server_by_tag.setdefault(tag_id, set()).add(rid)

            strategy = self._strategy
            push_queue = []

            for tag_id in COLLECTION_MAP.values():
                local_ids = set(tags_store.get_release_ids_for_tag(tag_id))
                server_ids = server_by_tag.get(tag_id, set())

                if strategy == MergeStrategy.PREFER_SERVER:
                    for rid in local_ids - server_ids:
                        tags_store.remove_release(tag_id, rid)
                    for rid in server_ids - local_ids:
                        tags_store.add_release(tag_id, rid)
                elif strategy == MergeStrategy.PREFER_LOCAL:
                    # Push local-only, remove server-only from server
                    for rid in local_ids - server_ids:
                        ctype = _TAG_TO_COLLECTION.get(tag_id)
                        if ctype:
                            push_queue.append((rid, ctype))
                    # Note: API doesn't support removing specific
                    # collection entries easily, skip for now
                else:
                    # MERGE
                    for rid in server_ids - local_ids:
                        tags_store.add_release(tag_id, rid)
                    for rid in local_ids - server_ids:
                        ctype = _TAG_TO_COLLECTION.get(tag_id)
                        if ctype:
                            push_queue.append((rid, ctype))

            self._push_collections(push_queue, then)

        self._client.get_collection_ids(on_server_collections)

    def _push_collections(self, queue, then):
        if not queue:
            then()
            return
        rid, ctype = queue.pop(0)
        self._client.add_to_collection(
            rid, ctype,
            lambda data, err: self._push_collections(queue, then))
