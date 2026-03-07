# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gtk

from kitsune.ui.image_cache import get_cache_size, clear_cache


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f'{size_bytes} B'
    elif size_bytes < 1024 * 1024:
        return f'{size_bytes / 1024:.1f} KB'
    elif size_bytes < 1024 * 1024 * 1024:
        return f'{size_bytes / (1024 * 1024):.1f} MB'
    return f'{size_bytes / (1024 * 1024 * 1024):.1f} GB'


class PreferencesWindow(Adw.PreferencesDialog):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._build_cache_page()

    def _build_cache_page(self):
        page = Adw.PreferencesPage(
            title=_('Cache'),
            icon_name='drive-harddisk-symbolic',
        )

        group = Adw.PreferencesGroup(
            title=_('Image Cache'),
            description=_('Cached poster images for offline access'),
        )

        # Cache size row
        self._cache_size_row = Adw.ActionRow(
            title=_('Cache Size'),
        )
        self._update_cache_size()
        group.add(self._cache_size_row)

        # Clear cache button row
        clear_row = Adw.ActionRow(
            title=_('Clear Cache'),
            subtitle=_('Remove all cached images'),
        )
        clear_btn = Gtk.Button(
            label=_('Clear'),
            valign=Gtk.Align.CENTER,
            css_classes=['destructive-action'],
        )
        clear_btn.connect('clicked', self._on_clear_clicked)
        clear_row.add_suffix(clear_btn)
        clear_row.set_activatable_widget(clear_btn)
        group.add(clear_row)

        page.add(group)
        self.add(page)

    def _update_cache_size(self):
        size = get_cache_size()
        self._cache_size_row.set_subtitle(_format_size(size))

    def _on_clear_clicked(self, _button):
        clear_cache()
        self._update_cache_size()
