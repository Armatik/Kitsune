# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk

from kitsune.api import AniLibriaClient
from kitsune.ui.genre_releases_view import GenreReleasesView
from kitsune.ui.widgets.content_grid import ContentGrid
from kitsune.ui.widgets.genre_card import GenreCard


class GenresView(Gtk.Box):

    def __init__(self, client: AniLibriaClient, auto_load: bool = True, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self._client = client
        self._on_release_activated = None
        self._on_navigation_changed = None
        self._releases_view = None
        self._current_genre = None
        self._narrow = False
        self._loaded = False

        self._stack = Gtk.Stack(
            transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT,
        )

        self._grid = ContentGrid()
        self._grid.set_on_child_activated(self._on_child_activated)
        self._stack.add_named(self._grid, 'grid')

        # Placeholder for releases (replaced when a genre is selected)
        self._releases_placeholder = Gtk.Box()
        self._stack.add_named(self._releases_placeholder, 'releases')

        self.append(self._stack)
        if auto_load:
            self.load()

    @property
    def in_releases(self) -> bool:
        return self._stack.get_visible_child_name() == 'releases'

    @property
    def current_genre_name(self) -> str:
        return self._current_genre.name if self._current_genre else ''

    def set_narrow(self, narrow: bool):
        self._narrow = narrow
        self._grid.set_narrow(narrow)
        if self._releases_view:
            self._releases_view.set_narrow(narrow)

    def set_on_release_activated(self, callback):
        self._on_release_activated = callback

    def set_on_navigation_changed(self, callback):
        self._on_navigation_changed = callback

    def go_back(self):
        self._stack.set_visible_child_name('grid')
        self._current_genre = None
        if self._on_navigation_changed:
            self._on_navigation_changed()

    def _show_genre_releases(self, genre):
        self._current_genre = genre

        old = self._stack.get_child_by_name('releases')
        if old:
            self._stack.remove(old)

        self._releases_view = GenreReleasesView(
            genre=genre, client=self._client,
        )
        self._releases_view.set_on_release_activated(self._on_release_activated)
        self._releases_view.set_narrow(self._narrow)
        self._stack.add_named(self._releases_view, 'releases')
        self._stack.set_visible_child_name('releases')

        if self._on_navigation_changed:
            self._on_navigation_changed()

    def load(self):
        if self._loaded:
            return
        self._loaded = True
        self._load_genres()

    def _load_genres(self):
        self._grid.set_spinner_visible(True)
        self._client.get_genres(callback=self._on_genres_loaded)

    def _on_genres_loaded(self, genres, error):
        self._grid.set_spinner_visible(False)
        if error or not genres:
            return
        for genre in sorted(genres, key=lambda g: g.name):
            self._grid.append_child(GenreCard(genre))

    def _on_child_activated(self, child):
        if isinstance(child, GenreCard):
            self._show_genre_releases(child.genre)
