# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gio, Gtk

from kitsune.ui.image_cache import get_cache_size, clear_cache

_STYLE_DESCRIPTIONS = {
    'classic': _('Standard layout without background effects'),
    'accent': _('Gradient background from poster accent colors'),
}


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f'{size_bytes} B'
    elif size_bytes < 1024 * 1024:
        return f'{size_bytes / 1024:.1f} KB'
    elif size_bytes < 1024 * 1024 * 1024:
        return f'{size_bytes / (1024 * 1024):.1f} MB'
    return f'{size_bytes / (1024 * 1024 * 1024):.1f} GB'


@Gtk.Template(resource_path='/net/armatik/Kitsune/preferences_window.ui')
class PreferencesWindow(Adw.PreferencesDialog):
    __gtype_name__ = 'KitsunePreferencesWindow'

    cache_size_row = Gtk.Template.Child()
    style_toggle = Gtk.Template.Child()
    style_description = Gtk.Template.Child()
    accent_group = Gtk.Template.Child()
    glass_effect_row = Gtk.Template.Child()
    color_points_row = Gtk.Template.Child()
    fade_duration_row = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._settings = Gio.Settings(schema_id='net.armatik.Kitsune')

        current = self._settings.get_string('release-page-style')
        self.style_toggle.set_active_name(current)
        self._update_style_description(current)
        self._update_accent_group_visibility(current)

        self.glass_effect_row.set_active(self._settings.get_boolean('accent-glass-effect'))
        self.glass_effect_row.connect('notify::active', self._on_glass_effect_changed)

        self.color_points_row.set_value(self._settings.get_int('accent-color-points'))
        self.fade_duration_row.set_value(self._settings.get_int('accent-fade-duration'))

        self.color_points_row.connect('notify::value', self._on_color_points_changed)
        self.fade_duration_row.connect('notify::value', self._on_fade_duration_changed)

        self._update_cache_size()

    def _update_style_description(self, name: str):
        self.style_description.set_label(
            _STYLE_DESCRIPTIONS.get(name, '')
        )

    def _update_accent_group_visibility(self, style: str):
        self.accent_group.set_visible(style == 'accent')

    def _update_cache_size(self):
        size = get_cache_size()
        self.cache_size_row.set_subtitle(_format_size(size))

    @Gtk.Template.Callback()
    def on_style_changed(self, toggle_group, _pspec):
        name = toggle_group.get_active_name()
        self._settings.set_string('release-page-style', name)
        self._update_style_description(name)
        self._update_accent_group_visibility(name)

    def _on_glass_effect_changed(self, row, _pspec):
        self._settings.set_boolean('accent-glass-effect', row.get_active())

    def _on_color_points_changed(self, row, _pspec):
        self._settings.set_int('accent-color-points', int(row.get_value()))

    def _on_fade_duration_changed(self, row, _pspec):
        self._settings.set_int('accent-fade-duration', int(row.get_value()))

    @Gtk.Template.Callback()
    def on_clear_clicked(self, _button):
        clear_cache()
        self._update_cache_size()
