# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json

import gi

gi.require_version('Soup', '3.0')

from gi.repository import GLib, Gio, Soup

from kitsune.models import CatalogResponse, Genre, Release


BASE_URL = 'https://anilibria.top/api/v1'


class AniLibriaClient:

    def __init__(self):
        self._session = Soup.Session()
        self._session.set_user_agent('Kitsune/0.1')

    def _fetch(self, path: str, callback, cancellable: Gio.Cancellable | None = None):
        uri = f'{BASE_URL}{path}'
        msg = Soup.Message.new('GET', uri)
        self._session.send_and_read_async(
            msg, GLib.PRIORITY_DEFAULT, cancellable,
            self._on_response, (callback, msg),
        )

    def _on_response(self, session, result, user_data):
        callback, msg = user_data
        try:
            gbytes = session.send_and_read_finish(result)
            status = msg.get_status()
            if status != Soup.Status.OK:
                callback(None, f'HTTP {status.value_nick}')
                return
            data = json.loads(gbytes.get_data())
            callback(data, None)
        except GLib.Error as e:
            if e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED):
                return
            callback(None, str(e))
        except Exception as e:
            callback(None, str(e))

    def get_catalog(self, page: int = 1, limit: int = 20,
                    filters: dict | None = None,
                    callback=None, cancellable=None):
        def on_data(data, error):
            if error:
                callback(None, error)
                return
            callback(CatalogResponse.from_dict(data), None)

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
        self._fetch(f'/anime/catalog/releases?{params}', on_data, cancellable)

    def search_releases(self, query: str, callback=None, cancellable=None):
        from urllib.parse import quote
        def on_data(data, error):
            if error:
                callback(None, error)
                return
            releases = [Release.from_dict(r) for r in data]
            callback(releases, None)

        self._fetch(f'/app/search/releases?query={quote(query)}', on_data, cancellable)

    def get_release(self, id_or_alias: str, callback=None, cancellable=None):
        from urllib.parse import quote
        def on_data(data, error):
            if error:
                callback(None, error)
                return
            callback(Release.from_dict(data), None)

        self._fetch(f'/anime/releases/{quote(str(id_or_alias))}', on_data, cancellable)

    def get_genres(self, callback=None, cancellable=None):
        def on_data(data, error):
            if error:
                callback(None, error)
                return
            genres = [Genre.from_dict(g) for g in data]
            callback(genres, None)

        self._fetch('/anime/genres', on_data, cancellable)

    def get_year_range(self, callback=None, cancellable=None):
        """Fetch min and max years from catalog. callback((min_year, max_year), error)."""
        result = {}

        def on_oldest(data, error):
            if error or not data:
                callback(None, error)
                return
            releases = data.get('data', [])
            result['min'] = releases[0]['year'] if releases else 2000
            self._fetch(
                '/anime/catalog/releases?page=1&limit=1&f%5Bsorting%5D=YEAR_DESC',
                on_newest, cancellable,
            )

        def on_newest(data, error):
            if error or not data:
                callback(None, error)
                return
            releases = data.get('data', [])
            result['max'] = releases[0]['year'] if releases else 2026
            callback((result['min'], result['max']), None)

        self._fetch(
            '/anime/catalog/releases?page=1&limit=1&f%5Bsorting%5D=YEAR_ASC',
            on_oldest, cancellable,
        )
