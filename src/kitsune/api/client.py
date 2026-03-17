# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json

import gi

gi.require_version('Soup', '3.0')

from gi.repository import GLib, Gio, Soup

from kitsune import API_BASE_URL
from kitsune.models import CatalogResponse, Franchise, Genre, Release
_REQUEST_TIMEOUT_MS = 10000
_OFFLINE_TIMEOUT_MS = 2000


def _make_callback(callback, parser):
    """Wrap a user callback with a parser for successful responses."""
    def on_data(data, error):
        if error:
            callback(None, error)
            return
        callback(parser(data), None)
    return on_data


class AniLibriaClient:

    def __init__(self):
        self._session = Soup.Session()
        self._session.set_user_agent('Kitsune/0.7.1')
        self._on_network_error = None
        self._on_network_ok = None
        self._offline = False

    def set_on_network_error(self, callback):
        self._on_network_error = callback

    def set_on_network_ok(self, callback):
        self._on_network_ok = callback

    def _fetch(self, path: str, callback, cancellable: Gio.Cancellable | None = None):
        uri = f'{API_BASE_URL}{path}'
        msg = Soup.Message.new('GET', uri)

        timeout_ms = _OFFLINE_TIMEOUT_MS if self._offline else _REQUEST_TIMEOUT_MS
        state = [False]  # [handled]

        def on_timeout():
            if not state[0]:
                state[0] = True
                self._offline = True
                callback(None, 'timeout')
                if self._on_network_error:
                    self._on_network_error()
            return GLib.SOURCE_REMOVE

        timeout_id = GLib.timeout_add(timeout_ms, on_timeout)

        self._session.send_and_read_async(
            msg, GLib.PRIORITY_DEFAULT, cancellable,
            self._on_response, (callback, msg, state, timeout_id),
        )

    def _handle_error(self, state, timeout_id, callback, error_msg):
        """Mark request handled, cancel timeout, always notify caller."""
        if state[0]:
            return
        state[0] = True
        GLib.source_remove(timeout_id)
        callback(None, error_msg)
        if not self._offline:
            self._offline = True
            if self._on_network_error:
                self._on_network_error()

    def _on_response(self, session, result, user_data):
        callback, msg, state, timeout_id = user_data
        if state[0]:
            return  # timeout already handled
        try:
            gbytes = session.send_and_read_finish(result)
            status = msg.get_status()
            if status != Soup.Status.OK:
                state[0] = True
                GLib.source_remove(timeout_id)
                callback(None, f'HTTP {status.value_nick}')
                return
            if gbytes is None:
                self._handle_error(state, timeout_id, callback,
                                   'Empty response')
                return
            state[0] = True
            GLib.source_remove(timeout_id)
            raw = gbytes.get_data()
            if len(raw) > 10 * 1024 * 1024:
                callback(None, 'Response too large')
                return
            data = json.loads(raw)
            callback(data, None)
            if self._offline:
                self._offline = False
                if self._on_network_ok:
                    self._on_network_ok()
        except GLib.Error as e:
            if e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED):
                if not state[0]:
                    state[0] = True
                    GLib.source_remove(timeout_id)
                return
            self._handle_error(state, timeout_id, callback, str(e))
        except Exception as e:
            self._handle_error(state, timeout_id, callback, str(e))

    def get_catalog(self, page: int = 1, limit: int = 20,
                    filters: dict | None = None,
                    callback=None, cancellable=None):
        params = f'page={page}&limit={limit}'
        if filters:
            from urllib.parse import quote
            for key, value in filters.items():
                if isinstance(value, dict):
                    for sub_key, sub_val in value.items():
                        params += f'&f%5B{quote(key)}%5D%5B{quote(sub_key)}%5D={quote(str(sub_val))}'
                elif isinstance(value, list):
                    for item in value:
                        params += f'&f%5B{quote(key)}%5D%5B%5D={quote(str(item))}'
                elif value is not None:
                    params += f'&f%5B{quote(key)}%5D={quote(str(value))}'
        self._fetch(f'/anime/catalog/releases?{params}',
                    _make_callback(callback, CatalogResponse.from_dict),
                    cancellable)

    def search_releases(self, query: str, callback=None, cancellable=None):
        from urllib.parse import quote
        self._fetch(f'/app/search/releases?query={quote(query)}',
                    _make_callback(callback, lambda d: [Release.from_dict(r) for r in d]),
                    cancellable)

    def get_release(self, id_or_alias: str, callback=None, cancellable=None):
        from urllib.parse import quote
        self._fetch(f'/anime/releases/{quote(str(id_or_alias))}',
                    _make_callback(callback, Release.from_dict),
                    cancellable)

    def get_release_raw(self, id_or_alias: str, callback=None, cancellable=None):
        from urllib.parse import quote
        self._fetch(f'/anime/releases/{quote(str(id_or_alias))}', callback, cancellable)

    def get_genres(self, callback=None, cancellable=None):
        self._fetch('/anime/genres',
                    _make_callback(callback, lambda d: [Genre.from_dict(g) for g in d]),
                    cancellable)

    def get_franchises(self, callback=None, cancellable=None):
        self._fetch('/anime/franchises',
                    _make_callback(callback, lambda d: [Franchise.from_dict(f) for f in d]),
                    cancellable)

    def get_franchise(self, franchise_id: str, callback=None, cancellable=None):
        from urllib.parse import quote
        self._fetch(f'/anime/franchises/{quote(franchise_id)}',
                    _make_callback(callback, Franchise.from_dict),
                    cancellable)

    def get_franchise_for_release(self, release_id: int, callback=None, cancellable=None):
        def on_data(data, error):
            if error:
                callback(None, error)
                return
            if isinstance(data, list) and data:
                callback(Franchise.from_dict(data[0]), None)
            else:
                callback(None, None)

        self._fetch(f'/anime/franchises/release/{release_id}', on_data, cancellable)

    def get_year_range(self, callback=None, cancellable=None):
        """Fetch min and max years from catalog. callback((min_year, max_year), error)."""
        import datetime
        result = {}

        def on_oldest(data, error):
            if error or not data:
                callback(None, error)
                return
            releases = data.get('data', [])
            result['min'] = releases[0].get('year', 2000) if releases else 2000
            self._fetch(
                '/anime/catalog/releases?page=1&limit=1&f%5Bsorting%5D=YEAR_DESC',
                on_newest, cancellable,
            )

        def on_newest(data, error):
            if error or not data:
                callback(None, error)
                return
            releases = data.get('data', [])
            result['max'] = releases[0].get('year', datetime.date.today().year) \
                if releases else datetime.date.today().year
            callback((result['min'], result['max']), None)

        self._fetch(
            '/anime/catalog/releases?page=1&limit=1&f%5Bsorting%5D=YEAR_ASC',
            on_oldest, cancellable,
        )
