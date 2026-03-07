# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gtk

from kitsune.models import Release
from kitsune.ui.image_cache import load_image


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

        # Poster container (overlay for spinner)
        self._overlay = Gtk.Overlay()
        self._overlay.set_size_request(180, 250)

        self._picture = Gtk.Picture()
        self._picture.set_size_request(180, 250)
        self._picture.set_content_fit(Gtk.ContentFit.COVER)
        self._picture.add_css_class('card')
        self._overlay.set_child(self._picture)

        # Spinner shown while loading
        self._spinner = Adw.Spinner()
        self._spinner.set_halign(Gtk.Align.CENTER)
        self._spinner.set_valign(Gtk.Align.CENTER)
        self._overlay.add_overlay(self._spinner)

        frame = Adw.Clamp(maximum_size=180)
        frame.set_child(self._overlay)
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
        load_image(url, self._on_poster_loaded)

    def _on_poster_loaded(self, texture, error):
        self._spinner.set_visible(False)
        if texture:
            self._picture.set_paintable(texture)
