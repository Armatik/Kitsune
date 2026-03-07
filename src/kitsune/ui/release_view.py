# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Soup', '3.0')

from gi.repository import Adw, Gdk, GLib, Gtk, Soup

from kitsune.api import AniLibriaClient
from kitsune.models import Release, Episode


class ReleaseView(Adw.NavigationPage):

    def __init__(self, release: Release, client: AniLibriaClient, **kwargs):
        super().__init__(title=release.name.main, **kwargs)
        self._release = release
        self._client = client
        self._on_episode_play = None
        self._build_ui()
        if not release.episodes:
            self._load_full_release()

    def set_on_episode_play(self, callback):
        self._on_episode_play = callback

    def _load_full_release(self):
        self._client.get_release(
            self._release.alias or str(self._release.id),
            callback=self._on_release_loaded,
        )

    def _on_release_loaded(self, release, error):
        if error or not release:
            return
        self._release = release
        self._populate_episodes()

    def _build_ui(self):
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())

        scrolled = Gtk.ScrolledWindow(vexpand=True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=24,
            margin_start=24,
            margin_end=24,
            margin_top=24,
            margin_bottom=24,
        )

        # Header: poster + info
        header = Gtk.Box(spacing=24)
        header.add_css_class('card')
        header.set_margin_bottom(12)

        self._poster = Gtk.Picture()
        self._poster.set_size_request(200, 280)
        self._poster.set_content_fit(Gtk.ContentFit.COVER)
        header.append(self._poster)

        if self._release.poster:
            self._load_poster(self._release.poster)

        info_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            valign=Gtk.Align.START,
            hexpand=True,
            margin_top=16,
            margin_bottom=16,
            margin_end=16,
        )

        title_label = Gtk.Label(
            label=self._release.name.main,
            wrap=True,
            xalign=0,
            css_classes=['title-1'],
        )
        info_box.append(title_label)

        if self._release.name.english:
            en_label = Gtk.Label(
                label=self._release.name.english,
                wrap=True,
                xalign=0,
                css_classes=['dim-label'],
            )
            info_box.append(en_label)

        # Metadata chips
        chips = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            max_children_per_line=10,
            row_spacing=4,
            column_spacing=4,
            margin_top=8,
        )

        meta_items = []
        if self._release.type:
            meta_items.append(self._release.type)
        if self._release.year:
            meta_items.append(str(self._release.year))
        if self._release.season:
            meta_items.append(self._release.season)
        if self._release.age_rating:
            meta_items.append(self._release.age_rating)

        for genre in self._release.genres:
            meta_items.append(genre.name)

        for item in meta_items:
            chip = Gtk.Label(label=item, css_classes=['caption', 'pill'])
            chip_child = Gtk.FlowBoxChild(focusable=False)
            chip_child.set_child(chip)
            chips.append(chip_child)

        info_box.append(chips)

        if self._release.description:
            desc = Gtk.Label(
                label=self._release.description,
                wrap=True,
                xalign=0,
                margin_top=12,
                selectable=True,
            )
            info_box.append(desc)

        header.append(info_box)
        content.append(header)

        # Episodes section
        episodes_label = Gtk.Label(
            label=_('Episodes'),
            xalign=0,
            css_classes=['title-3'],
        )
        content.append(episodes_label)

        self._episodes_list = Gtk.ListBox(
            selection_mode=Gtk.SelectionMode.NONE,
            css_classes=['boxed-list'],
        )
        content.append(self._episodes_list)

        self._populate_episodes()

        scrolled.set_child(content)
        toolbar.set_content(scrolled)
        self.set_child(toolbar)

    def _populate_episodes(self):
        while child := self._episodes_list.get_first_child():
            self._episodes_list.remove(child)

        for episode in self._release.episodes:
            row = Adw.ActionRow(
                title=self._episode_title(episode),
                subtitle=self._episode_subtitle(episode),
                activatable=True,
            )
            play_btn = Gtk.Button(
                icon_name='media-playback-start-symbolic',
                valign=Gtk.Align.CENTER,
                css_classes=['flat'],
            )
            play_btn.connect('clicked', self._on_play_clicked, episode)
            row.add_suffix(play_btn)
            row.connect('activated', lambda _r, ep=episode: self._play_episode(ep))
            self._episodes_list.append(row)

    def _episode_title(self, episode: Episode) -> str:
        ordinal = int(episode.ordinal) if episode.ordinal == int(episode.ordinal) else episode.ordinal
        if episode.name:
            return f'{ordinal}. {episode.name}'
        return _('Episode {}').format(ordinal)

    def _episode_subtitle(self, episode: Episode) -> str:
        parts = []
        if episode.duration:
            mins = episode.duration // 60
            parts.append(f'{mins} ' + _('min'))
        qualities = []
        if episode.hls_1080:
            qualities.append('1080p')
        if episode.hls_720:
            qualities.append('720p')
        if episode.hls_480:
            qualities.append('480p')
        if qualities:
            parts.append(' / '.join(qualities))
        return ' — '.join(parts) if parts else ''

    def _on_play_clicked(self, _button, episode):
        self._play_episode(episode)

    def _play_episode(self, episode: Episode):
        if self._on_episode_play:
            self._on_episode_play(self._release, episode)

    def _load_poster(self, url: str):
        session = Soup.Session()
        msg = Soup.Message.new('GET', url)
        session.send_and_read_async(
            msg, GLib.PRIORITY_DEFAULT, None,
            self._on_poster_loaded, None,
        )

    def _on_poster_loaded(self, session, result, _data):
        try:
            gbytes = session.send_and_read_finish(result)
            texture = Gdk.Texture.new_from_bytes(gbytes)
            self._poster.set_paintable(texture)
        except Exception:
            pass
