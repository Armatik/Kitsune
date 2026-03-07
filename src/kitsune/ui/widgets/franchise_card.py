# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gtk

from kitsune.models import Franchise
from kitsune.ui.image_cache import load_image


class FranchiseCard(Gtk.FlowBoxChild):

    def __init__(self, franchise: Franchise, **kwargs):
        super().__init__(**kwargs)
        self.franchise = franchise
        self._build_ui()
        if franchise.image:
            self._load_image(franchise.image)

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

        self._overlay = Gtk.Overlay()
        self._overlay.set_size_request(180, 250)

        self._picture = Gtk.Picture()
        self._picture.set_size_request(180, 250)
        self._picture.set_content_fit(Gtk.ContentFit.COVER)
        self._picture.add_css_class('card')
        self._overlay.set_child(self._picture)

        self._spinner = Adw.Spinner()
        self._spinner.set_halign(Gtk.Align.CENTER)
        self._spinner.set_valign(Gtk.Align.CENTER)
        self._overlay.add_overlay(self._spinner)

        frame = Adw.Clamp(maximum_size=180)
        frame.set_child(self._overlay)
        box.append(frame)

        # Title
        title = Gtk.Label(
            label=self.franchise.name,
            wrap=True,
            max_width_chars=20,
            lines=2,
            ellipsize=3,
            xalign=0,
            css_classes=['heading'],
        )
        box.append(title)

        # Subtitle: years + release count
        parts = []
        if self.franchise.first_year:
            if self.franchise.last_year and self.franchise.last_year != self.franchise.first_year:
                parts.append(f'{self.franchise.first_year}–{self.franchise.last_year}')
            else:
                parts.append(str(self.franchise.first_year))
        if self.franchise.total_releases:
            parts.append(f'{self.franchise.total_releases} ' + _('titles'))
        if parts:
            subtitle = Gtk.Label(
                label=' / '.join(parts),
                xalign=0,
                css_classes=['dim-label', 'caption'],
            )
            box.append(subtitle)

        self.set_child(box)

    def _load_image(self, url: str):
        load_image(url, self._on_image_loaded)

    def _on_image_loaded(self, texture, error):
        self._spinner.set_visible(False)
        if texture:
            self._picture.set_paintable(texture)
