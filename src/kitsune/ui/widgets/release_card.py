# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gdk, Gtk

from kitsune.models import Release
from kitsune import tags_store
from kitsune.ui.image_cache import load_image


@Gtk.Template(resource_path='/net/armatik/Kitsune/release_card.ui')
class ReleaseCard(Gtk.FlowBoxChild):
    __gtype_name__ = 'KitsuneReleaseCard'

    picture = Gtk.Template.Child()
    placeholder = Gtk.Template.Child()
    spinner = Gtk.Template.Child()
    title_label = Gtk.Template.Child()
    subtitle_label = Gtk.Template.Child()
    tag_badges = Gtk.Template.Child()

    _badge_css_loaded = False

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

    @classmethod
    def _ensure_badge_css(cls):
        if cls._badge_css_loaded:
            return
        cls._badge_css_loaded = True
        css = Gtk.CssProvider()
        css.load_from_string(
            '.tag-badge { min-width: 24px; min-height: 24px;'
            ' border-radius: 50%; background: alpha(black, 0.6);'
            ' border: 1.5px solid alpha(white, 0.12); }'
            ' .tag-badge-plus { background: alpha(@accent_bg_color, 0.3);'
            ' border-color: alpha(@accent_bg_color, 0.5); }'
            ' .tag-badge-emoji { font-size: 13px; }'
            ' .tag-badge-color { min-width: 14px; min-height: 14px;'
            ' border-radius: 50%; }'
        )
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _populate_tag_badges(self):
        self._ensure_badge_css()
        tags = tags_store.get_tags_for_release(self.release.id)
        if not tags:
            return

        self.tag_badges.set_visible(True)
        max_visible = 3
        visible_tags = tags[:max_visible]
        has_more = len(tags) > max_visible

        for i, tag in enumerate(visible_tags):
            badge = Gtk.Box(
                halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
                css_classes=['tag-badge'],
            )
            if i > 0:
                badge.set_margin_start(-6)
            if tag['icon_type'] == 'emoji':
                badge.append(Gtk.Label(
                    label=tag['icon_value'],
                    css_classes=['tag-badge-emoji'],
                ))
            else:
                from kitsune.ui.widgets.tag_card import COLOR_MAP
                hex_c = COLOR_MAP.get(tag['icon_value'], '#6e7781')
                circle = Gtk.Box(css_classes=['tag-badge-color'])
                c_css = Gtk.CssProvider()
                c_css.load_from_string(
                    f'.tag-badge-color {{ background: {hex_c}; }}'
                )
                circle.get_style_context().add_provider(
                    c_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
                )
                badge.append(circle)
            self.tag_badges.append(badge)

        if has_more:
            plus = Gtk.Box(
                halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
                css_classes=['tag-badge', 'tag-badge-plus'],
                margin_start=-6,
            )
            plus.append(Gtk.Label(label='+', css_classes=['accent']))
            self.tag_badges.append(plus)

    def _on_preview_loaded(self, texture, error):
        if texture and not self.picture.get_paintable():
            self.picture.set_paintable(texture)

    def _on_poster_loaded(self, texture, error):
        self.spinner.set_visible(False)
        if texture:
            self.picture.set_paintable(texture)
        elif not self.picture.get_paintable():
            self.placeholder.set_visible(True)
