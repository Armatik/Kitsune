# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import GLib, Gtk

from kitsune.api import AniLibriaClient
from kitsune.ui.franchise_releases_view import FranchiseReleasesView
from kitsune.ui.widgets.content_grid import ContentGrid
from kitsune.ui.widgets.franchise_card import FranchiseCard


class FranchisesView(Gtk.Box):

    def __init__(self, client: AniLibriaClient, auto_load: bool = True, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self._client = client
        self._on_release_activated = None
        self._on_navigation_changed = None
        self._releases_view = None
        self._current_franchise = None
        self._narrow = False
        self._loaded = False

        self._stack = Gtk.Stack(
            transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT,
        )

        self._grid = ContentGrid()
        self._grid.set_on_child_activated(self._on_child_activated)
        self._stack.add_named(self._grid, 'grid')

        self._releases_placeholder = Gtk.Box()
        self._stack.add_named(self._releases_placeholder, 'releases')

        self.append(self._stack)
        if auto_load:
            self.load()

    @property
    def in_releases(self) -> bool:
        return self._stack.get_visible_child_name() == 'releases'

    @property
    def current_franchise_name(self) -> str:
        return self._current_franchise.name if self._current_franchise else ''

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
        self._current_franchise = None
        if self._on_navigation_changed:
            self._on_navigation_changed()

    def _show_franchise_releases(self, franchise):
        self._current_franchise = franchise

        old = self._stack.get_child_by_name('releases')
        if old:
            self._stack.remove(old)

        self._releases_view = FranchiseReleasesView(
            franchise=franchise, client=self._client,
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
        self._load_franchises()

    def _load_franchises(self):
        self._grid.set_spinner_visible(True)
        self._client.get_franchises(callback=self._on_franchises_loaded)

    def _on_franchises_loaded(self, franchises, error):
        if error or not franchises:
            self._grid.set_spinner_visible(False)
            return
        self._pending_franchises = sorted(franchises, key=lambda f: f.name)
        self._add_pending_batch()

    def _add_pending_batch(self):
        batch = self._pending_franchises[:4]
        self._pending_franchises = self._pending_franchises[4:]
        for franchise in batch:
            self._grid.append_child(FranchiseCard(franchise))
        if self._pending_franchises:
            GLib.idle_add(self._add_pending_batch)
        else:
            self._grid.set_spinner_visible(False)

    def _on_child_activated(self, child):
        if isinstance(child, FranchiseCard):
            self._show_franchise_releases(child.franchise)
