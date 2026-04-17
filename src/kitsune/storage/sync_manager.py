# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import time

from gi.repository import GLib

from kitsune.storage import tags_store, watch_positions
from kitsune.storage.pending_queue import (
    PendingQueue, OP_ADD_FAVORITE, OP_REMOVE_FAVORITE,
    OP_ADD_COLLECTION, OP_REMOVE_COLLECTION, OP_SAVE_TIMECODE,
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


def _parse_timecode_item(item):
    """Parse a server timecode entry. Returns (episode_id, time, is_watched, updated_at) or None.

    When `updated_at` is missing (None) we fall back to `time.time()` — server
    is "fresh" by default. We distinguish missing from 0: `updated_at = 0` is
    an explicit epoch timestamp and is preserved so conflict resolution can
    compare it correctly (it will lose to any positive local timestamp).
    """
    if isinstance(item, (list, tuple)) and len(item) >= 3:
        ep_id, time_val, is_watched = item[0], item[1], item[2]
        updated_at = item[3] if len(item) >= 4 and item[3] is not None else time.time()
        return (ep_id, float(time_val), bool(is_watched), float(updated_at))
    if isinstance(item, dict):
        ep_id = item.get('episode_id') or item.get('id')
        if not ep_id:
            return None
        raw_updated_at = item.get('updated_at')
        updated_at = time.time() if raw_updated_at is None else raw_updated_at
        return (
            ep_id,
            float(item.get('time', 0)),
            bool(item.get('is_watched', False)),
            float(updated_at),
        )
    return None


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
        self._pull_snapshot = set()
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

        Two-phase dispatch:
          1. Non-timecode ops: one at a time through the callback chain.
          2. Timecode ops: batched into one save_timecodes call (cap 50).

        Unknown op kinds (added by a newer version and loaded from disk on
        an older binary) are skipped but NOT removed — the op stays in the
        queue until a version that understands it runs and drains. This
        prevents silent data loss during downgrades.
        """
        ready = self._queue.peek_ready(time.time())
        # Prefer non-timecode ops first
        non_tc_op = None
        non_tc_method = None
        for candidate in ready:
            if candidate.op == OP_SAVE_TIMECODE:
                continue
            method = self._OP_DISPATCH.get(candidate.op)
            if method:
                non_tc_op = candidate
                non_tc_method = method
                break
            log.debug(
                'Skipping unknown op kind %r in queue (op id %s) — '
                'leaving in place for a future version', candidate.op, candidate.id)
        if non_tc_op is not None:
            self._queue.mark_in_flight(non_tc_op.id)
            getattr(self, non_tc_method)(non_tc_op)
            return
        # No non-timecode ops ready — batch timecodes
        timecode_ops = [op for op in ready if op.op == OP_SAVE_TIMECODE][:50]
        if timecode_ops:
            self._dispatch_timecode_batch(timecode_ops)
            return
        # Nothing to dispatch (everything left is unknown op kinds)
        self._draining = False

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

    def _dispatch_timecode_batch(self, ops):
        """Send a batch of save_timecode ops in one HTTP call.

        All ops are marked in-flight together. On 2xx response, all are
        mark_success'd. On error, all are mark_failure'd with the same
        error — the next retry tick may re-batch them (possibly with
        different coalescing neighbours).
        """
        for op in ops:
            self._queue.mark_in_flight(op.id)
        timecodes = [op.payload for op in ops]
        op_ids = [op.id for op in ops]
        self._client.save_timecodes(
            timecodes,
            lambda data, err: self._on_timecode_batch_result(ops, op_ids, err))

    def _on_timecode_batch_result(self, ops, op_ids, error):
        """Handle the result of a batched save_timecodes call.

        Uses the same exception-safety guard as `_on_op_result` — if a
        subscriber raises or mark_success/failure raises, we reset
        `_draining` and re-schedule so the pipeline does not deadlock.
        """
        try:
            if error:
                for op in ops:
                    self._queue.mark_failure(op.id, str(error))
                    self._emit_sync_error(op.op, op.release_id, str(error))
                self._emit_queue_changed()
            else:
                for op_id in op_ids:
                    self._queue.mark_success(op_id)
                self._emit_queue_changed()
            self._drain_next()
        except Exception:
            log.exception('Timecode batch result handler raised; resetting drain state')
            self._draining = False
            self._schedule_drain()

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

        If a drain is already in progress (`_draining=True`), the
        `_drain_queue` call hits the reentrancy guard and returns
        immediately. The `reset_all_retries()` call above still took
        effect, so every op is now ready — the in-progress drain will
        pick them up as it iterates. The user's click therefore always
        has an effect, even when the dispatch itself appears to be a no-op.
        """
        self._queue.reset_all_retries()
        self._drain_queue()

    # --- Initial sync with strategy ---

    def initial_sync(self, callback=None, strategy=MergeStrategy.MERGE):
        """Full sync with chosen merge strategy.

        Before the server HTTP pull begins, a snapshot of pending-queue
        release ids is captured into `self._pull_snapshot`. During the
        sync, `_sync_favorites` and `_sync_collections` skip any release
        id in the snapshot — pending ops own those releases until they
        drain. The queue is also kicked via `_schedule_drain()` as a
        best-effort flush, but the snapshot is taken BEFORE the kick so
        even successfully-drained ops in this tick remain protected
        against read-after-write replication lag on the server.
        """
        if self._syncing:
            log.debug('Sync already in progress, skipping')
            if callback:
                callback(False, 'already_syncing')
            return
        self._syncing = True
        log.debug('Starting sync with strategy: %s', strategy)
        self._strategy = strategy
        # Snapshot before kicking drain (see docstring). The snapshot and
        # the drain kick are deliberately independent: we always try to
        # drain (it's cheap on an empty queue), and the snapshot freezes
        # the release-ids owned by pending ops so the concurrent pull
        # does not stomp them.
        self._pull_snapshot = self._queue.release_ids()
        if self._pull_snapshot:
            log.debug('Pull snapshot holds %d release ids', len(self._pull_snapshot))
        self._schedule_drain()
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

    def enqueue_timecode(self, release_id: int, episode_id: str,
                        pos: float, is_watched: bool):
        """Enqueue a timecode save for the server.

        Stage 1 coalescing ensures rapid saves for the same
        (release_id, episode_id) update an existing op in place rather
        than stacking duplicates. Called by player_view on every local
        save_position / mark_completed.

        The ordinal is intentionally NOT in this signature — the server
        identifies episodes by episode_id alone, and coalescing in
        PendingQueue uses (release_id, episode_id) as the key. The local
        save (via watch_positions.save_position) is where ordinal is
        needed, and player_view calls that separately.
        """
        if not self.is_logged_in():
            return
        self._queue.enqueue(
            OP_SAVE_TIMECODE, release_id, user_id=self._user_id,
            payload={
                'episode_id': episode_id,
                'time': pos,
                'is_watched': is_watched,
            })
        self._emit_queue_changed()
        self._schedule_drain()

    # --- Watch positions ---

    def flush_timecodes(self, release_id=None, callback=None):
        """Enqueue every pushable local entry and drain.

        Called on player exit and app close (window.py:100). Since
        Stage 2, the queue is the single path to the server — this method
        used to build its own payload but now delegates to enqueue +
        drain. Coalescing ensures no duplicate ops for the same
        (release_id, episode_id).

        If release_id is given, only entries for that release are flushed.

        The callback argument is accepted for backward compat with the
        old synchronous signature but is invoked immediately — the actual
        server write happens asynchronously via the queue.
        """
        if not self.is_logged_in():
            if callback:
                callback(True, None)
            return
        for rid, ordinal, entry in watch_positions.iter_pushable():
            if release_id is not None and rid != release_id:
                continue
            pos = entry['pos']
            is_watched = (pos == -1)
            self._queue.enqueue(
                OP_SAVE_TIMECODE, rid, user_id=self._user_id,
                payload={
                    'episode_id': entry['episode_id'],
                    'time': pos if not is_watched else 0,
                    'is_watched': is_watched,
                })
        self._emit_queue_changed()
        self._schedule_drain()
        if callback:
            callback(True, None)

    def _pull_and_save_timecodes(self, then):
        """Pull watch positions from server and apply them locally.

        Server may return either list-of-lists (`[episode_id, time,
        is_watched]`) or list-of-dicts (`{episode_id, time, is_watched,
        updated_at}`). Each entry is resolved via
        `watch_positions.apply_server_entry` which handles the episode_id
        → (release_id, ordinal) mapping (with episode_index fallback).

        Entries whose episode_id cannot be resolved are silently skipped
        (counted as 'unmapped' in the debug log). Conflict resolution is
        local-wins-on-tie per A4 — the server only overwrites when its
        `updated_at` is strictly greater than the local one.
        """
        if not self.is_logged_in():
            then()
            return

        def on_timecodes(data, error):
            if error:
                log.debug('Timecodes pull failed: %s', error)
                then()
                return
            applied = skipped = unmapped = 0
            for item in (data or []):
                parsed = _parse_timecode_item(item)
                if parsed is None:
                    continue
                ep_id, time_val, is_watched, updated_at = parsed
                result = watch_positions.apply_server_entry(
                    ep_id, time_val, is_watched, updated_at)
                if result == 'applied':
                    applied += 1
                elif result == 'skipped':
                    skipped += 1
                elif result == 'unmapped':
                    unmapped += 1
            log.debug('Timecodes pulled: applied=%d skipped=%d unmapped=%d',
                      applied, skipped, unmapped)
            then()

        self._client.get_timecodes(callback=on_timecodes)

    def pull_timecodes(self, callback=None):
        """Public wrapper around _pull_and_save_timecodes for backward compat."""
        if not self.is_logged_in():
            if callback:
                callback(True, None)
            return
        def then():
            if callback:
                callback(True, None)
        self._pull_and_save_timecodes(then)

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
        self._pull_snapshot = set()
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
            snapshot = self._pull_snapshot

            if strategy == MergeStrategy.PREFER_SERVER:
                # Clear local, set to server — BUT skip snapshot ids
                # (pending queue owns them)
                for rid in (local_ids - server_set) - snapshot:
                    tags_store.remove_release('favorites', rid)
                for rid in (server_set - local_ids) - snapshot:
                    tags_store.add_release('favorites', rid)
                then()
            elif strategy == MergeStrategy.PREFER_LOCAL:
                # Push all local to server — snapshot ids go via queue
                to_add = (local_ids - server_set) - snapshot
                to_remove = (server_set - local_ids) - snapshot
                if to_add:
                    self._client.add_favorites(list(to_add), _noop)
                if to_remove:
                    self._client.remove_favorites(list(to_remove), _noop)
                then()
            else:
                # MERGE: server wins conflicts — snapshot ids excluded
                for rid in (server_set - local_ids) - snapshot:
                    tags_store.add_release('favorites', rid)
                local_only = (local_ids - server_set) - snapshot
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
            snapshot = self._pull_snapshot
            push_queue = []

            for tag_id in COLLECTION_MAP.values():
                local_ids = set(tags_store.get_release_ids_for_tag(tag_id))
                server_ids = server_by_tag.get(tag_id, set())

                if strategy == MergeStrategy.PREFER_SERVER:
                    for rid in (local_ids - server_ids) - snapshot:
                        tags_store.remove_release(tag_id, rid)
                    for rid in (server_ids - local_ids) - snapshot:
                        tags_store.add_release(tag_id, rid)
                elif strategy == MergeStrategy.PREFER_LOCAL:
                    for rid in (local_ids - server_ids) - snapshot:
                        ctype = _TAG_TO_COLLECTION.get(tag_id)
                        if ctype:
                            push_queue.append((rid, ctype))
                else:
                    # MERGE
                    for rid in (server_ids - local_ids) - snapshot:
                        tags_store.add_release(tag_id, rid)
                    for rid in (local_ids - server_ids) - snapshot:
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
