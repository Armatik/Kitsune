# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gio, GLib, Gtk

from kitsune.api import AniLibriaClient
from kitsune.ui.widgets.release_card import ReleaseCard


@Gtk.Template(resource_path='/net/armatik/Kitsune/search_view.ui')
class SearchView(Adw.NavigationPage):
    __gtype_name__ = 'KitsuneSearchView'

    search_entry = Gtk.Template.Child()
    stack = Gtk.Template.Child()
    flowbox = Gtk.Template.Child()

    def __init__(self, client: AniLibriaClient, **kwargs):
        super().__init__(**kwargs)
        self._client = client
        self._cancellable = None
        self._debounce_id = 0
        self._on_release_activated = None

    def set_on_release_activated(self, callback):
        self._on_release_activated = callback

    @Gtk.Template.Callback()
    def on_search_changed(self, entry):
        if self._debounce_id:
            GLib.source_remove(self._debounce_id)
        query = entry.get_text().strip()
        if len(query) < 2:
            self.stack.set_visible_child_name('empty')
            return
        self._debounce_id = GLib.timeout_add(300, self._do_search, query)

    def _do_search(self, query):
        self._debounce_id = 0
        if self._cancellable:
            self._cancellable.cancel()
        self._cancellable = Gio.Cancellable()

        self.stack.set_visible_child_name('loading')

        self._client.search_releases(
            query=query,
            callback=self._on_search_results,
            cancellable=self._cancellable,
        )
        return GLib.SOURCE_REMOVE

    def _on_search_results(self, releases, error):
        if error:
            self.stack.set_visible_child_name('empty')
            return

        while child := self.flowbox.get_first_child():
            self.flowbox.remove(child)

        if not releases:
            self.stack.set_visible_child_name('no-results')
            return

        for release in releases:
            card = ReleaseCard(release)
            self.flowbox.append(card)

        self.stack.set_visible_child_name('results')

    @Gtk.Template.Callback()
    def on_child_activated(self, _flowbox, child):
        if self._on_release_activated and isinstance(child, ReleaseCard):
            self._on_release_activated(child.release)

    def grab_focus(self):
        self.search_entry.grab_focus()
        return True
