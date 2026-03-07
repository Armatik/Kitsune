# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gtk

from kitsune.models import Release
from kitsune.ui.image_cache import load_image


@Gtk.Template(resource_path='/net/armatik/Kitsune/release_card.ui')
class ReleaseCard(Gtk.FlowBoxChild):
    __gtype_name__ = 'KitsuneReleaseCard'

    picture = Gtk.Template.Child()
    spinner = Gtk.Template.Child()
    title_label = Gtk.Template.Child()
    subtitle_label = Gtk.Template.Child()

    def __init__(self, release: Release, **kwargs):
        super().__init__(**kwargs)
        self.release = release

        self.title_label.set_label(release.name.main)

        subtitle_parts = []
        if release.type:
            subtitle_parts.append(release.type)
        if release.year:
            subtitle_parts.append(str(release.year))
        if subtitle_parts:
            self.subtitle_label.set_label(' / '.join(subtitle_parts))
            self.subtitle_label.set_visible(True)

        if release.poster:
            load_image(release.poster, self._on_poster_loaded)

    def _on_poster_loaded(self, texture, error):
        self.spinner.set_visible(False)
        if texture:
            self.picture.set_paintable(texture)
