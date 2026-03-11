# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gio, Gtk

from kitsune.ui.image_cache import get_cache_size, get_cache_count, clear_cache
from kitsune import release_cache, watch_positions, tags_store
from kitsune.navbar import (
    ALL_TAB_IDS, get_tab, ensure_complete, parse_tab_order, serialize_tab_order,
)

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
    preview_count_row = Gtk.Template.Child()
    preview_size_row = Gtk.Template.Child()
    release_count_row = Gtk.Template.Child()
    release_size_row = Gtk.Template.Child()
    watch_count_row = Gtk.Template.Child()
    watch_size_row = Gtk.Template.Child()
    tags_count_row = Gtk.Template.Child()
    tags_size_row = Gtk.Template.Child()
    style_toggle = Gtk.Template.Child()
    style_description = Gtk.Template.Child()
    accent_group = Gtk.Template.Child()
    mobile_enabled_row = Gtk.Template.Child()
    glass_effect_row = Gtk.Template.Child()
    color_points_row = Gtk.Template.Child()
    fade_duration_row = Gtk.Template.Child()
    close_button_row = Gtk.Template.Child()
    navbar_sync_row = Gtk.Template.Child()
    navbar_desktop_group = Gtk.Template.Child()
    navbar_desktop_list = Gtk.Template.Child()
    navbar_mobile_group = Gtk.Template.Child()
    navbar_mobile_list = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._settings = Gio.Settings(schema_id='net.armatik.Kitsune')

        current = self._settings.get_string('release-page-style')
        self.style_toggle.set_active_name(current)
        self._update_style_description(current)
        self._update_accent_group_visibility(current)

        self.mobile_enabled_row.set_active(self._settings.get_boolean('accent-mobile-enabled'))
        self.mobile_enabled_row.connect('notify::active', self._on_mobile_enabled_changed)

        self.glass_effect_row.set_active(self._settings.get_boolean('accent-glass-effect'))
        self.glass_effect_row.connect('notify::active', self._on_glass_effect_changed)

        self.color_points_row.set_value(self._settings.get_int('accent-color-points'))
        self.fade_duration_row.set_value(self._settings.get_int('accent-fade-duration'))

        self.color_points_row.connect('notify::value', self._on_color_points_changed)
        self.fade_duration_row.connect('notify::value', self._on_fade_duration_changed)

        self.close_button_row.set_active(
            self._settings.get_boolean('player-show-close-button'))
        self.close_button_row.connect('notify::active', self._on_close_button_changed)

        self._update_cache_size()
        self._update_preview_cache()
        self._update_release_cache()
        self._update_watch_progress()
        self._update_tags()
        self._setup_navbar_prefs()

    def _update_style_description(self, name: str):
        self.style_description.set_label(
            _STYLE_DESCRIPTIONS.get(name, '')
        )

    def _update_accent_group_visibility(self, style: str):
        self.accent_group.set_visible(style == 'accent')

    def _update_cache_size(self):
        count = get_cache_count('posters')
        size = get_cache_size('posters')
        self.cache_size_row.set_subtitle(
            f'{count} — {_format_size(size)}')

    def _update_preview_cache(self):
        count = get_cache_count('previews')
        size = get_cache_size('previews')
        self.preview_count_row.set_subtitle(str(count))
        self.preview_size_row.set_subtitle(_format_size(size))

    @Gtk.Template.Callback()
    def on_style_changed(self, toggle_group, _pspec):
        name = toggle_group.get_active_name()
        self._settings.set_string('release-page-style', name)
        self._update_style_description(name)
        self._update_accent_group_visibility(name)

    def _on_mobile_enabled_changed(self, row, _pspec):
        self._settings.set_boolean('accent-mobile-enabled', row.get_active())

    def _on_glass_effect_changed(self, row, _pspec):
        self._settings.set_boolean('accent-glass-effect', row.get_active())

    def _on_color_points_changed(self, row, _pspec):
        self._settings.set_int('accent-color-points', int(row.get_value()))

    def _on_fade_duration_changed(self, row, _pspec):
        self._settings.set_int('accent-fade-duration', int(row.get_value()))

    def _on_close_button_changed(self, row, _pspec):
        self._settings.set_boolean('player-show-close-button', row.get_active())

    def _update_watch_progress(self):
        count = watch_positions.get_count()
        size = watch_positions.get_size()
        self.watch_count_row.set_subtitle(str(count))
        self.watch_size_row.set_subtitle(_format_size(size))

    def _update_release_cache(self):
        count = release_cache.get_count()
        size = release_cache.get_size()
        self.release_count_row.set_subtitle(str(count))
        self.release_size_row.set_subtitle(_format_size(size))

    @Gtk.Template.Callback()
    def on_clear_release_clicked(self, _button):
        release_cache.clear_all()
        self._update_release_cache()

    @Gtk.Template.Callback()
    def on_clear_clicked(self, _button):
        clear_cache('posters')
        self._update_cache_size()

    @Gtk.Template.Callback()
    def on_clear_preview_clicked(self, _button):
        clear_cache('previews')
        self._update_preview_cache()

    @Gtk.Template.Callback()
    def on_clear_progress_clicked(self, _button):
        watch_positions.clear_all()
        self._update_watch_progress()

    def _update_tags(self):
        count = tags_store.get_count()
        size = tags_store.get_size()
        self.tags_count_row.set_subtitle(str(count))
        self.tags_size_row.set_subtitle(_format_size(size))

    @Gtk.Template.Callback()
    def on_clear_tags_clicked(self, _button):
        tags_store.clear_all()
        self._update_tags()

    # --- Navigation Preferences ---

    _NAV_TAB_LABELS = {
        'catalog': _('Catalog'),
        'genres': _('Genres'),
        'franchises': _('Franchises'),
        'tags': _('Favorites & Tags'),
    }

    def _setup_navbar_prefs(self):
        self.navbar_sync_row.set_active(
            self._settings.get_boolean('navbar-sync'))
        self.navbar_sync_row.connect(
            'notify::active', self._on_navbar_sync_changed)

        self._rebuild_navbar_list('navbar-desktop', self.navbar_desktop_list)
        self._rebuild_navbar_list('navbar-mobile', self.navbar_mobile_list)
        self._update_mobile_sensitivity()

    def _update_mobile_sensitivity(self):
        is_sync = self.navbar_sync_row.get_active()
        self.navbar_mobile_group.set_sensitive(not is_sync)

    def _on_navbar_sync_changed(self, row, _pspec):
        self._settings.set_boolean('navbar-sync', row.get_active())
        self._update_mobile_sensitivity()

    def _rebuild_navbar_list(self, settings_key, listbox):
        """Build a tab list with visibility toggles."""
        while True:
            row = listbox.get_row_at_index(0)
            if row is None:
                break
            listbox.remove(row)

        visible_ids = parse_tab_order(
            self._settings.get_string(settings_key))
        all_ids = ensure_complete(visible_ids)
        visible_set = set(visible_ids)

        # Store switch refs: {settings_key: [(tab_id, switch), ...]}
        if not hasattr(self, '_navbar_switches'):
            self._navbar_switches = {}
        self._navbar_switches[settings_key] = []

        for tab_id in all_ids:
            tab = get_tab(tab_id)
            if not tab:
                continue

            row = Adw.ActionRow(
                title=self._NAV_TAB_LABELS.get(tab_id, tab['label']),
                icon_name=tab['icon'],
            )

            switch = Gtk.Switch(valign=Gtk.Align.CENTER,
                                active=tab_id in visible_set)
            switch.connect('notify::active',
                           self._on_tab_visibility_changed,
                           settings_key)
            row.add_suffix(switch)
            listbox.append(row)
            self._navbar_switches[settings_key].append((tab_id, switch))

    def _on_tab_visibility_changed(self, switch, _pspec, settings_key):
        entries = self._navbar_switches.get(settings_key, [])
        visible = [tid for tid, sw in entries if sw.get_active()]
        if not visible:
            visible = [ALL_TAB_IDS[0]]
        self._settings.set_string(settings_key, serialize_tab_order(visible))
