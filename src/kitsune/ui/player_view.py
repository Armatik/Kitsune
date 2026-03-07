# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gio, GLib, Gtk

from kitsune.models import Episode, Release
from kitsune.player.gst_player import GstPlayer


class PlayerView(Adw.NavigationPage):

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
        self._build_ui()
        self._connect_signals()
        self._start_playback()

    def _build_ui(self):
        overlay = Gtk.Overlay()

        # Video area
        if self._player.paintable:
            self._picture = Gtk.Picture.new_for_paintable(self._player.paintable)
        else:
            self._picture = Gtk.Picture()

        self._picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self._picture.set_hexpand(True)
        self._picture.set_vexpand(True)
        overlay.set_child(self._picture)

        # Top bar with title
        self._top_bar = Gtk.Box(
            valign=Gtk.Align.START,
            css_classes=['osd'],
            margin_start=12,
            margin_end=12,
            margin_top=12,
        )
        back_btn = Gtk.Button(icon_name='go-previous-symbolic', css_classes=['flat'])
        back_btn.connect('clicked', lambda _: self._on_back())
        self._top_bar.append(back_btn)

        ordinal = int(self._episode.ordinal) if self._episode.ordinal == int(self._episode.ordinal) else self._episode.ordinal
        title_label = Gtk.Label(
            label=f'{self._release.name.main} — {_("Episode")} {ordinal}',
            hexpand=True,
            ellipsize=3,
            css_classes=['heading'],
            margin_start=8,
        )
        self._top_bar.append(title_label)
        overlay.add_overlay(self._top_bar)

        # Controls overlay
        self._controls = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            valign=Gtk.Align.END,
            css_classes=['osd'],
            margin_start=12,
            margin_end=12,
            margin_bottom=12,
            spacing=8,
        )

        # Progress bar
        self._progress = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL,
            hexpand=True,
            draw_value=False,
        )
        self._progress.set_range(0, 100)
        self._progress.connect('change-value', self._on_seek)
        self._controls.append(self._progress)

        # Button row
        btn_row = Gtk.Box(
            spacing=8,
            halign=Gtk.Align.CENTER,
            margin_bottom=4,
        )

        # Time label
        self._time_label = Gtk.Label(label='0:00 / 0:00', css_classes=['caption'])
        btn_row.append(self._time_label)

        # Rewind
        rw_btn = Gtk.Button(icon_name='media-seek-backward-symbolic', css_classes=['flat', 'circular'])
        rw_btn.connect('clicked', lambda _: self._player.seek(max(0, self._player.get_position() - 10)))
        btn_row.append(rw_btn)

        # Play/Pause
        self._play_btn = Gtk.Button(icon_name='media-playback-start-symbolic', css_classes=['flat', 'circular'])
        self._play_btn.connect('clicked', lambda _: self._player.toggle_play_pause())
        btn_row.append(self._play_btn)

        # Forward
        ff_btn = Gtk.Button(icon_name='media-seek-forward-symbolic', css_classes=['flat', 'circular'])
        ff_btn.connect('clicked', lambda _: self._player.seek(self._player.get_position() + 10))
        btn_row.append(ff_btn)

        # Quality selector
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
            self._quality_dropdown = Gtk.DropDown(model=quality_model)
            preferred = self._settings.get_string('preferred-quality')
            if preferred in available_qualities:
                self._quality_dropdown.set_selected(available_qualities.index(preferred))
            self._quality_dropdown.connect('notify::selected', self._on_quality_changed)
            btn_row.append(self._quality_dropdown)

        self._controls.append(btn_row)

        # Skip intro/outro button
        self._skip_btn = Gtk.Button(
            label=_('Skip Intro'),
            css_classes=['pill', 'suggested-action'],
            visible=False,
            halign=Gtk.Align.END,
            valign=Gtk.Align.END,
            margin_end=24,
            margin_bottom=100,
        )
        self._skip_btn.connect('clicked', self._on_skip)
        overlay.add_overlay(self._skip_btn)

        overlay.add_overlay(self._controls)

        # Click to toggle controls
        click = Gtk.GestureClick()
        click.connect('released', self._on_click)
        overlay.add_controller(click)

        self.set_child(overlay)

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
            self._progress.set_range(0, duration)
            self._progress.set_value(position)
        self._time_label.set_label(
            f'{self._fmt_time(position)} / {self._fmt_time(duration)}'
        )
        self._update_skip_button(position)

    def _update_skip_button(self, position):
        op = self._episode.opening
        ed = self._episode.ending
        if op and op.start <= position <= op.stop:
            self._skip_btn.set_label(_('Skip Intro'))
            self._skip_btn.set_visible(True)
            self._skip_target = op.stop
        elif ed and ed.start <= position <= ed.stop:
            self._skip_btn.set_label(_('Skip Outro'))
            self._skip_btn.set_visible(True)
            self._skip_target = ed.stop
        else:
            self._skip_btn.set_visible(False)
            self._skip_target = None

    def _on_skip(self, _btn):
        if self._skip_target:
            self._player.seek(self._skip_target)

    def _on_seek(self, _scale, _scroll_type, value):
        self._seeking = True
        self._player.seek(value)
        GLib.timeout_add(200, self._reset_seeking)
        return False

    def _reset_seeking(self):
        self._seeking = False
        return GLib.SOURCE_REMOVE

    def _on_state_changed(self, _player, state):
        if state == 'playing':
            self._play_btn.set_icon_name('media-playback-pause-symbolic')
        else:
            self._play_btn.set_icon_name('media-playback-start-symbolic')

    def _on_eos(self, _player):
        self._on_back()

    def _on_error(self, _player, message):
        toast = Adw.Toast(title=_('Playback error: {}').format(message))
        root = self.get_root()
        if hasattr(root, 'add_toast'):
            root.add_toast(toast)

    def _on_quality_changed(self, dropdown, _pspec):
        idx = dropdown.get_selected()
        if idx < len(self._available_qualities):
            quality = self._available_qualities[idx]
            self._settings.set_string('preferred-quality', quality)
            position = self._player.get_position()
            url = self._episode.get_hls_url(quality)
            if url:
                self._player.play_uri(url)
                GLib.timeout_add(500, lambda: self._player.seek(position) or GLib.SOURCE_REMOVE)

    def _on_click(self, _gesture, _n_press, _x, _y):
        if self._controls_visible:
            self._hide_controls()
        else:
            self._show_controls()
            self._schedule_hide_controls()

    def _show_controls(self):
        self._controls.set_visible(True)
        self._top_bar.set_visible(True)
        self._controls_visible = True

    def _hide_controls(self):
        self._controls.set_visible(False)
        self._top_bar.set_visible(False)
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

    def _on_back(self):
        self._player.cleanup()
        nav = self.get_ancestor(Adw.NavigationView)
        if nav:
            nav.pop()

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
