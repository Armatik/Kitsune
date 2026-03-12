# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gtk

from kitsune.models import Release
from kitsune import tags_store
from kitsune.ui import register_css
from kitsune.ui.image_cache import load_image

_BADGE_CSS = (
    '.tag-badge-pill { padding: 5px 8px; border-radius: 9999px;'
    ' background: alpha(@accent_bg_color, 0.85); }'
    ' .tag-badge-pill image { -gtk-icon-style: symbolic;'
    ' color: @accent_fg_color; }'
    ' .tag-badge-emoji { font-size: 16px; }'
)


@Gtk.Template(resource_path='/net/armatik/Kitsune/release_card.ui')
class ReleaseCard(Gtk.FlowBoxChild):
    __gtype_name__ = 'KitsuneReleaseCard'

    picture = Gtk.Template.Child()
    placeholder = Gtk.Template.Child()
    spinner = Gtk.Template.Child()
    title_label = Gtk.Template.Child()
    subtitle_label = Gtk.Template.Child()
    tag_badges = Gtk.Template.Child()

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
            if release.poster_preview:
                load_image(release.poster_preview, self._on_preview_loaded)
            load_image(release.poster, self._on_poster_loaded)
        elif release.poster_preview:
            load_image(release.poster_preview, self._on_poster_loaded)
        else:
            self.spinner.set_visible(False)
            self.placeholder.set_visible(True)

        self._populate_tag_badges()

    def _populate_tag_badges(self):
        register_css(_BADGE_CSS)
        tags = tags_store.get_tags_for_release(self.release.id)
        if not tags:
            return

        self.tag_badges.set_visible(True)
        max_visible = 3
        visible_tags = tags[:max_visible]
        has_more = len(tags) > max_visible

        pill = Gtk.Box(
            spacing=4,
            halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
            css_classes=['tag-badge-pill'],
        )

        for tag in visible_tags:
            if tag['icon_type'] == 'emoji':
                pill.append(Gtk.Label(
                    label=tag['icon_value'],
                    css_classes=['tag-badge-emoji'],
                ))
            else:
                from kitsune.ui.widgets.tag_card import create_color_circle
                pill.append(create_color_circle(tag['icon_value'], 16))

        if has_more:
            pill.append(Gtk.Image(
                icon_name='net.armatik.Kitsune.plus-circle-symbolic',
                pixel_size=16,
                valign=Gtk.Align.CENTER,
            ))

        self.tag_badges.append(pill)

    def refresh_tag_badges(self):
        while child := self.tag_badges.get_first_child():
            self.tag_badges.remove(child)
        self.tag_badges.set_visible(False)
        self._populate_tag_badges()

    def _on_preview_loaded(self, texture, error):
        if texture and not self.picture.get_paintable():
            self.picture.set_paintable(texture)

    def _on_poster_loaded(self, texture, error):
        self.spinner.set_visible(False)
        if texture:
            self.picture.set_paintable(texture)
        elif not self.picture.get_paintable():
            self.placeholder.set_visible(True)
