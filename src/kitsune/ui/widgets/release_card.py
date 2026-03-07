# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Soup', '3.0')

from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Soup

from kitsune.models import Release

_image_session = Soup.Session()


class ReleaseCard(Gtk.FlowBoxChild):

    def __init__(self, release: Release, **kwargs):
        super().__init__(**kwargs)
        self.release = release
        self._build_ui()
        if release.poster:
            self._load_poster(release.poster)

    def _build_ui(self):
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
            margin_start=6,
            margin_end=6,
            margin_top=6,
            margin_bottom=6,
        )
        box.set_size_request(180, -1)

        # Poster
        self._picture = Gtk.Picture()
        self._picture.set_size_request(180, 250)
        self._picture.set_content_fit(Gtk.ContentFit.COVER)
        self._picture.add_css_class('card')

        frame = Adw.Clamp(maximum_size=180)
        frame.set_child(self._picture)
        box.append(frame)

        # Title
        title = Gtk.Label(
            label=self.release.name.main,
            wrap=True,
            max_width_chars=20,
            lines=2,
            ellipsize=3,  # PANGO_ELLIPSIZE_END
            xalign=0,
            css_classes=['heading'],
        )
        box.append(title)

        # Subtitle: type + year
        subtitle_parts = []
        if self.release.type:
            subtitle_parts.append(self.release.type)
        if self.release.year:
            subtitle_parts.append(str(self.release.year))
        if subtitle_parts:
            subtitle = Gtk.Label(
                label=' / '.join(subtitle_parts),
                xalign=0,
                css_classes=['dim-label', 'caption'],
            )
            box.append(subtitle)

        self.set_child(box)

    def _load_poster(self, url: str):
        msg = Soup.Message.new('GET', url)
        _image_session.send_and_read_async(
            msg, GLib.PRIORITY_DEFAULT, None,
            self._on_poster_loaded, None,
        )

    def _on_poster_loaded(self, session, result, _data):
        try:
            gbytes = session.send_and_read_finish(result)
            texture = Gdk.Texture.new_from_bytes(gbytes)
            self._picture.set_paintable(texture)
        except Exception:
            pass  # Keep placeholder on error
