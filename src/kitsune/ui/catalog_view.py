# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gtk, GLib

from kitsune.api import AniLibriaClient
from kitsune.ui.widgets.release_card import ReleaseCard


class CatalogView(Adw.NavigationPage):

    def __init__(self, client: AniLibriaClient, **kwargs):
        super().__init__(title=_('Catalog'), tag='catalog', **kwargs)
        self._client = client
        self._page = 0
        self._last_page = 1
        self._loading = False
        self._on_release_activated = None
        self._build_ui()
        self._load_next_page()

    def set_on_release_activated(self, callback):
        self._on_release_activated = callback

    def _build_ui(self):
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())

        scrolled = Gtk.ScrolledWindow(vexpand=True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        vadjustment = scrolled.get_vadjustment()
        vadjustment.connect('value-changed', self._on_scroll)

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

        self._spinner = Gtk.Spinner(spinning=True, margin_top=24, margin_bottom=24)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_box.append(self._flowbox)
        content_box.append(self._spinner)

        scrolled.set_child(content_box)
        toolbar.set_content(scrolled)
        self.set_child(toolbar)

    def _on_scroll(self, adjustment):
        if self._loading:
            return
        value = adjustment.get_value()
        upper = adjustment.get_upper()
        page_size = adjustment.get_page_size()
        if value + page_size >= upper - 200:
            self._load_next_page()

    def _load_next_page(self):
        if self._page >= self._last_page:
            self._spinner.set_visible(False)
            return
        self._loading = True
        self._page += 1
        self._spinner.set_visible(True)
        self._client.get_catalog(
            page=self._page, limit=20,
            callback=self._on_catalog_loaded,
        )

    def _on_catalog_loaded(self, catalog_response, error):
        self._loading = False
        self._spinner.set_spinning(False)
        self._spinner.set_visible(False)

        if error:
            toast = Adw.Toast(title=_('Failed to load catalog'))
            root = self.get_root()
            if hasattr(root, 'add_toast'):
                root.add_toast(toast)
            return

        self._last_page = catalog_response.meta.last_page
        for release in catalog_response.releases:
            card = ReleaseCard(release)
            self._flowbox.append(card)

    def _on_child_activated(self, _flowbox, child):
        if self._on_release_activated and isinstance(child, ReleaseCard):
            self._on_release_activated(child.release)
