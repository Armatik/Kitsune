# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import GLib, Gtk

from kitsune.api import AniLibriaClient
from kitsune.ui.filter_dialog import FilterDialog
from kitsune.ui.widgets.content_grid import ContentGrid
from kitsune.ui.widgets.release_card import ReleaseCard


class CatalogView(Gtk.Box):

    def __init__(self, client: AniLibriaClient, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self._client = client
        self._page = 0
        self._last_page = 1
        self._loading = False
        self._reached_end = False
        self._on_release_activated = None
        self._filters: dict = {}
        self._genres_data: list = []
        self._year_range: tuple[int, int] | None = None

        self._grid = ContentGrid()
        self._grid.set_on_scroll_near_end(self._on_scroll_near_end)
        self._grid.set_on_child_activated(self._on_child_activated)
        self.append(self._grid)

        self._load_next_page()

    @property
    def flowbox(self):
        return self._grid.flowbox

    def set_narrow(self, narrow: bool):
        self._grid.set_narrow(narrow)

    def set_on_release_activated(self, callback):
        self._on_release_activated = callback

    def open_filter_dialog(self):
        if not self._genres_data:
            self._load_genres()
        if not self._year_range:
            self._load_year_range()
        dialog = FilterDialog(genres=self._genres_data, year_range=self._year_range)
        dialog.set_filters(self._filters)
        dialog.set_on_apply(self._on_filters_applied)
        dialog.present(self.get_root())

    def _load_genres(self):
        self._client.get_genres(callback=self._on_genres_loaded)

    def _on_genres_loaded(self, genres, error):
        if genres:
            self._genres_data = [{'id': g.id, 'name': g.name} for g in genres]

    def _load_year_range(self):
        self._client.get_year_range(callback=self._on_year_range_loaded)

    def _on_year_range_loaded(self, year_range, error):
        if year_range:
            self._year_range = year_range

    def _on_filters_applied(self, filters: dict):
        self._filters = filters
        self._reset_catalog()
        self._load_next_page()

    def _reset_catalog(self):
        self._page = 0
        self._last_page = 1
        self._loading = False
        self._reached_end = False
        self._grid.clear()

    def _on_scroll_near_end(self):
        if not self._loading and not self._reached_end:
            self._load_next_page()

    def _load_next_page(self):
        if self._page >= self._last_page:
            self._show_end()
            return
        self._loading = True
        self._page += 1
        self._grid.set_spinner_visible(True)
        self._client.get_catalog(
            page=self._page, limit=20,
            filters=self._filters or None,
            callback=self._on_catalog_loaded,
        )

    def retry(self):
        self._grid.clear_error()
        self._loading = False
        self._reached_end = False
        self._load_next_page()

    def _on_catalog_loaded(self, catalog_response, error):
        self._loading = False

        if error:
            self._page = max(0, self._page - 1)
            self._grid.show_error()
            return

        self._last_page = catalog_response.meta.last_page
        self._pending_releases = list(catalog_response.releases)
        self._add_pending_batch()

    def _add_pending_batch(self):
        if not self.get_mapped():
            return GLib.SOURCE_REMOVE
        batch = self._pending_releases[:4]
        self._pending_releases = self._pending_releases[4:]
        for release in batch:
            self._grid.append_child(ReleaseCard(release))

        if self._pending_releases:
            GLib.idle_add(self._add_pending_batch)
        else:
            self._grid.set_spinner_visible(False)
            if self._page >= self._last_page:
                self._show_end()

    def _show_end(self):
        self._reached_end = True
        self._grid.show_end()

    def _on_child_activated(self, child):
        if self._on_release_activated and isinstance(child, ReleaseCard):
            self._on_release_activated(child.release)
