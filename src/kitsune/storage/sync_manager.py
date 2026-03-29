# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import time

from kitsune.storage import tags_store, watch_positions

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
        """Add release to tag locally + push to server."""
        tags_store.add_release(tag_id, release_id)
        if not self.is_logged_in():
            return
        if tag_id == 'favorites':
            self._client.add_favorites([release_id], _noop)
        elif tag_id in _TAG_TO_COLLECTION:
            self._client.add_to_collection(
                release_id, _TAG_TO_COLLECTION[tag_id], _noop)

    def remove_from_tag_synced(self, tag_id, release_id):
        """Remove release from tag locally + push to server."""
        tags_store.remove_release(tag_id, release_id)
        if not self.is_logged_in():
            return
        if tag_id == 'favorites':
            self._client.remove_favorites([release_id], _noop)
        elif tag_id in _TAG_TO_COLLECTION:
            self._client.remove_from_collection([release_id], _noop)

    def toggle_favorite_synced(self, release_id):
        """Toggle favorite locally + push to server. Returns new state."""
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
