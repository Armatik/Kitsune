# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gio, GLib, Gtk

from kitsune.models import Episode, Release
from kitsune.player.gst_player import GstPlayer


@Gtk.Template(resource_path='/net/armatik/Kitsune/player_view.ui')
class PlayerView(Adw.NavigationPage):
    __gtype_name__ = 'KitsunePlayerView'

    picture = Gtk.Template.Child()
    top_bar = Gtk.Template.Child()
    title_label = Gtk.Template.Child()
    controls = Gtk.Template.Child()
    progress = Gtk.Template.Child()
    time_label = Gtk.Template.Child()
    play_btn = Gtk.Template.Child()
    quality_dropdown = Gtk.Template.Child()
    skip_btn = Gtk.Template.Child()

    def __init__(self, release: Release, episode: Episode, **kwargs):
        super().__init__(title=release.name.main, **kwargs)
        self._release = release
        self._episode = episode
        self._player = GstPlayer()
        self._controls_visible = True
        self._hide_timer = 0
        self._seeking = False
        self._skip_target = None
        self._settings = Gio.Settings(schema_id='net.armatik.Kitsune')

        self._setup_title()
        self._setup_paintable()
        self._setup_quality()
        self._setup_click_handler()
        self._connect_signals()
        self._start_playback()

    def _setup_title(self):
        ordinal = int(self._episode.ordinal) if self._episode.ordinal == int(self._episode.ordinal) else self._episode.ordinal
        self.title_label.set_label(
            f'{self._release.name.main} — {_("Episode")} {ordinal}'
        )

    def _setup_paintable(self):
        if self._player.paintable:
            self.picture.set_paintable(self._player.paintable)

    def _setup_quality(self):
        quality_model = Gtk.StringList()
        available_qualities = []
        if self._episode.hls_1080:
            quality_model.append('1080p')
            available_qualities.append('1080')
        if self._episode.hls_720:
            quality_model.append('720p')
            available_qualities.append('720')
        if self._episode.hls_480:
            quality_model.append('480p')
            available_qualities.append('480')

        self._available_qualities = available_qualities

        if len(available_qualities) > 1:
            self.quality_dropdown.set_model(quality_model)
            self.quality_dropdown.set_visible(True)
            preferred = self._settings.get_string('preferred-quality')
            if preferred in available_qualities:
                self.quality_dropdown.set_selected(available_qualities.index(preferred))

    def _setup_click_handler(self):
        click = Gtk.GestureClick()
        click.connect('released', self._on_click)
        overlay = self.get_child()
        overlay.add_controller(click)

    def _connect_signals(self):
        self._player.connect('position-updated', self._on_position_updated)
        self._player.connect('state-changed', self._on_state_changed)
        self._player.connect('eos', self._on_eos)
        self._player.connect('error', self._on_error)

    def _start_playback(self):
        quality = self._settings.get_string('preferred-quality')
        url = self._episode.get_hls_url(quality)
        if url:
            self._player.play_uri(url)
            self._schedule_hide_controls()

    def _on_position_updated(self, _player, position, duration):
        if duration > 0 and not self._seeking:
            self.progress.set_range(0, duration)
            self.progress.set_value(position)
        self.time_label.set_label(
            f'{self._fmt_time(position)} / {self._fmt_time(duration)}'
        )
        self._update_skip_button(position)

    def _update_skip_button(self, position):
        op = self._episode.opening
        ed = self._episode.ending
        if op and op.start <= position <= op.stop:
            self.skip_btn.set_label(_('Skip Intro'))
            self.skip_btn.set_visible(True)
            self._skip_target = op.stop
        elif ed and ed.start <= position <= ed.stop:
            self.skip_btn.set_label(_('Skip Outro'))
            self.skip_btn.set_visible(True)
            self._skip_target = ed.stop
        else:
            self.skip_btn.set_visible(False)
            self._skip_target = None

    def _on_state_changed(self, _player, state):
        if state == 'playing':
            self.play_btn.set_icon_name('media-playback-pause-symbolic')
        else:
            self.play_btn.set_icon_name('media-playback-start-symbolic')

    def _on_eos(self, _player):
        self._do_back()

    def _on_error(self, _player, message):
        toast = Adw.Toast(title=_('Playback error: {}').format(message))
        root = self.get_root()
        if hasattr(root, 'add_toast'):
            root.add_toast(toast)

    def _on_click(self, _gesture, _n_press, _x, _y):
        if self._controls_visible:
            self._hide_controls()
        else:
            self._show_controls()
            self._schedule_hide_controls()

    def _show_controls(self):
        self.controls.set_visible(True)
        self.top_bar.set_visible(True)
        self._controls_visible = True

    def _hide_controls(self):
        self.controls.set_visible(False)
        self.top_bar.set_visible(False)
        self._controls_visible = False

    def _schedule_hide_controls(self):
        if self._hide_timer:
            GLib.source_remove(self._hide_timer)
        self._hide_timer = GLib.timeout_add_seconds(3, self._auto_hide_controls)

    def _auto_hide_controls(self):
        self._hide_timer = 0
        if self._player.is_playing:
            self._hide_controls()
        return GLib.SOURCE_REMOVE

    def _do_back(self):
        self._player.cleanup()
        nav = self.get_ancestor(Adw.NavigationView)
        if nav:
            nav.pop()

    @Gtk.Template.Callback()
    def on_back(self, _button):
        self._do_back()

    @Gtk.Template.Callback()
    def on_seek(self, _scale, _scroll_type, value):
        self._seeking = True
        self._player.seek(value)
        GLib.timeout_add(200, self._reset_seeking)
        return False

    def _reset_seeking(self):
        self._seeking = False
        return GLib.SOURCE_REMOVE

    @Gtk.Template.Callback()
    def on_rewind(self, _button):
        self._player.seek(max(0, self._player.get_position() - 10))

    @Gtk.Template.Callback()
    def on_play_pause(self, _button):
        self._player.toggle_play_pause()

    @Gtk.Template.Callback()
    def on_forward(self, _button):
        self._player.seek(self._player.get_position() + 10)

    @Gtk.Template.Callback()
    def on_quality_changed(self, dropdown, _pspec):
        idx = dropdown.get_selected()
        if idx < len(self._available_qualities):
            quality = self._available_qualities[idx]
            self._settings.set_string('preferred-quality', quality)
            position = self._player.get_position()
            url = self._episode.get_hls_url(quality)
            if url:
                self._player.play_uri(url)
                GLib.timeout_add(500, lambda: self._player.seek(position) or GLib.SOURCE_REMOVE)

    @Gtk.Template.Callback()
    def on_skip(self, _btn):
        if self._skip_target:
            self._player.seek(self._skip_target)

    @staticmethod
    def _fmt_time(seconds: int) -> str:
        m, s = divmod(max(0, seconds), 60)
        h, m = divmod(m, 60)
        if h:
            return f'{h}:{m:02d}:{s:02d}'
        return f'{m}:{s:02d}'

    def do_unmap(self):
        self._player.cleanup()
        Adw.NavigationPage.do_unmap(self)
