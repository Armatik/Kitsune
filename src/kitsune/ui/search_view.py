# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gio, GLib, Gtk

from kitsune.api import AniLibriaClient
from kitsune.ui.widgets.release_card import ReleaseCard


class SearchView(Adw.NavigationPage):

    def __init__(self, client: AniLibriaClient, **kwargs):
        super().__init__(title=_('Search'), tag='search', **kwargs)
        self._client = client
        self._cancellable = None
        self._debounce_id = 0
        self._on_release_activated = None
        self._build_ui()

    def set_on_release_activated(self, callback):
        self._on_release_activated = callback

    def _build_ui(self):
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        self._search_entry = Gtk.SearchEntry(
            placeholder_text=_('Search anime...'),
            hexpand=True,
        )
        self._search_entry.connect('search-changed', self._on_search_changed)
        header.set_title_widget(self._search_entry)

        scrolled = Gtk.ScrolledWindow(vexpand=True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._stack = Gtk.Stack()

        # Empty state
        self._status_page = Adw.StatusPage(
            title=_('Search for Anime'),
            description=_('Enter a title name to find it'),
            icon_name='system-search-symbolic',
        )
        self._stack.add_named(self._status_page, 'empty')

        # Results
        self._flowbox = Gtk.FlowBox(
            homogeneous=True,
            min_children_per_line=2,
            max_children_per_line=6,
            column_spacing=12,
            row_spacing=12,
            margin_start=12,
            margin_end=12,
            margin_top=12,
            margin_bottom=12,
            selection_mode=Gtk.SelectionMode.NONE,
            activate_on_single_click=True,
        )
        self._flowbox.connect('child-activated', self._on_child_activated)
        self._stack.add_named(self._flowbox, 'results')

        # Loading
        spinner = Gtk.Spinner(spinning=True)
        spinner_box = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, vexpand=True)
        spinner_box.append(spinner)
        self._stack.add_named(spinner_box, 'loading')

        # No results
        no_results = Adw.StatusPage(
            title=_('No Results'),
            description=_('Try a different search query'),
            icon_name='system-search-symbolic',
        )
        self._stack.add_named(no_results, 'no-results')

        scrolled.set_child(self._stack)
        toolbar.set_content(scrolled)
        self.set_child(toolbar)

    def _on_search_changed(self, entry):
        if self._debounce_id:
            GLib.source_remove(self._debounce_id)
        query = entry.get_text().strip()
        if len(query) < 2:
            self._stack.set_visible_child_name('empty')
            return
        self._debounce_id = GLib.timeout_add(300, self._do_search, query)

    def _do_search(self, query):
        self._debounce_id = 0
        if self._cancellable:
            self._cancellable.cancel()
        self._cancellable = Gio.Cancellable()

        self._stack.set_visible_child_name('loading')

        self._client.search_releases(
            query=query,
            callback=self._on_search_results,
            cancellable=self._cancellable,
        )
        return GLib.SOURCE_REMOVE

    def _on_search_results(self, releases, error):
        if error:
            self._stack.set_visible_child_name('empty')
            return

        # Clear previous results
        while child := self._flowbox.get_first_child():
            self._flowbox.remove(child)

        if not releases:
            self._stack.set_visible_child_name('no-results')
            return

        for release in releases:
            card = ReleaseCard(release)
            self._flowbox.append(card)

        self._stack.set_visible_child_name('results')

    def _on_child_activated(self, _flowbox, child):
        if self._on_release_activated and isinstance(child, ReleaseCard):
            self._on_release_activated(child.release)

    def grab_focus(self):
        self._search_entry.grab_focus()
        return True
