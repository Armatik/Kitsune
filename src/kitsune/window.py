# SPDX-License-Identifier: GPL-3.0-or-later

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gtk, Gio


class KitsuneWindow(Adw.ApplicationWindow):

    def __init__(self, **kwargs):
        super().__init__(
            default_width=900,
            default_height=600,
            **kwargs,
        )
        self._settings = Gio.Settings(schema_id='net.armatik.Kitsune')
        self._setup_window_state()
        self._build_ui()

    def _setup_window_state(self):
        self.set_default_size(
            self._settings.get_int('window-width'),
            self._settings.get_int('window-height'),
        )
        self.connect('close-request', self._on_close_request)

    def _on_close_request(self, _window):
        size = self.get_default_size()
        self._settings.set_int('window-width', size[0])
        self._settings.set_int('window-height', size[1])

    def _build_ui(self):
        self._split_view = Adw.NavigationSplitView()
        self.set_content(self._split_view)

        # Sidebar
        sidebar_page = Adw.NavigationPage(title='Kitsune')
        sidebar_toolbar = Adw.ToolbarView()
        sidebar_header = Adw.HeaderBar()
        sidebar_toolbar.add_top_bar(sidebar_header)

        self._sidebar_list = Gtk.ListBox(css_classes=['navigation-sidebar'])
        self._sidebar_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._sidebar_list.connect('row-activated', self._on_sidebar_row_activated)

        catalog_row = Adw.ActionRow(title=_('Catalog'), icon_name='view-grid-symbolic')
        search_row = Adw.ActionRow(title=_('Search'), icon_name='system-search-symbolic')
        self._sidebar_list.append(catalog_row)
        self._sidebar_list.append(search_row)

        sidebar_toolbar.set_content(self._sidebar_list)
        sidebar_page.set_child(sidebar_toolbar)

        # Content
        self._content_nav = Adw.NavigationView()

        placeholder = Adw.StatusPage(
            title=_('Kitsune'),
            description=_('Select a section from the sidebar'),
            icon_name='net.armatik.Kitsune',
        )
        content_toolbar = Adw.ToolbarView()
        content_toolbar.add_top_bar(Adw.HeaderBar())
        content_toolbar.set_content(placeholder)

        content_page = Adw.NavigationPage(title='Kitsune', tag='placeholder')
        content_page.set_child(content_toolbar)
        self._content_nav.push(content_page)

        self._split_view.set_sidebar(sidebar_page)
        self._split_view.set_content(self._content_nav)

        self._sidebar_list.select_row(self._sidebar_list.get_row_at_index(0))

    def _on_sidebar_row_activated(self, _listbox, row):
        index = row.get_index()
        if index == 0:
            self._show_catalog()
        elif index == 1:
            self._show_search()

    def _show_catalog(self):
        pass  # Will be implemented later

    def _show_search(self):
        pass  # Will be implemented later
