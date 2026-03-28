# SPDX-License-Identifier: GPL-3.0-or-later

import time

from kitsune.storage import tags_store

_COLLECTION_MAP = {
    'WATCHING': 'watching',
    'WATCHED': 'watched',
    'PLANNED': 'planned',
    'POSTPONED': 'postponed',
    'ABANDONED': 'abandoned',
}

_TAG_TO_COLLECTION = {v: k for k, v in _COLLECTION_MAP.items()}


def _noop(data, error):
    """No-op callback for fire-and-forget API calls."""
    pass


class SyncManager:
    def __init__(self, client):
        self._client = client
        self._last_sync = None

    def get_last_sync_time(self):
        return self._last_sync

    def initial_sync(self, callback=None):
        self._sync_favorites(lambda: self._sync_collections(lambda: self._sync_done(callback)))

    def sync_now(self, callback=None):
        self.initial_sync(callback)

    def _sync_done(self, callback):
        self._last_sync = time.time()
        if callback:
            callback(True, None)

    def _sync_favorites(self, then):
        def on_server_favs(server_ids, error):
            if error:
                then()
                return
            local_ids = set(tags_store.get_release_ids_for_tag('favorites'))
            server_set = set(server_ids) if server_ids else set()
            for rid in server_set - local_ids:
                tags_store.add_release('favorites', rid)
            local_only = local_ids - server_set
            if local_only:
                self._client.add_favorites(list(local_only), lambda data, err: then())
            else:
                then()
        self._client.get_favorite_ids(on_server_favs)

    def _sync_collections(self, then):
        def on_server_collections(server_entries, error):
            if error:
                then()
                return
            server_by_tag = {}
            for entry in (server_entries or []):
                rid = entry.get('release_id', 0) if isinstance(entry, dict) else 0
                ctype = entry.get('type_of_collection', '') if isinstance(entry, dict) else ''
                tag_id = _COLLECTION_MAP.get(ctype)
                if tag_id and rid:
                    server_by_tag.setdefault(tag_id, set()).add(rid)
            push_queue = []
            for tag_id in _COLLECTION_MAP.values():
                local_ids = set(tags_store.get_release_ids_for_tag(tag_id))
                server_ids = server_by_tag.get(tag_id, set())
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
        self._client.add_to_collection(rid, ctype, lambda data, err: self._push_collections(queue, then))

    def add_to_tag_synced(self, tag_id, release_id):
        tags_store.add_release(tag_id, release_id)
        if tag_id == 'favorites':
            self._client.add_favorites([release_id], _noop)
        elif tag_id in _TAG_TO_COLLECTION:
            self._client.add_to_collection(release_id, _TAG_TO_COLLECTION[tag_id], _noop)

    def remove_from_tag_synced(self, tag_id, release_id):
        tags_store.remove_release(tag_id, release_id)
        if tag_id == 'favorites':
            self._client.remove_favorites([release_id], _noop)
        elif tag_id in _TAG_TO_COLLECTION:
            self._client.remove_from_collection([release_id], _noop)
