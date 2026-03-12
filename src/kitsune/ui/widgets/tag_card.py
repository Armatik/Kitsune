# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gdk, Gtk

from kitsune.ui import register_css

COLOR_MAP = {
    'blue': '#3584e4',
    'teal': '#2190a4',
    'green': '#3a944a',
    'yellow': '#c88800',
    'orange': '#e66100',
    'red': '#c01c28',
    'pink': '#d56199',
    'purple': '#9141ac',
    'slate': '#6e7781',
}

def create_color_circle(color_name: str, size: int = 28) -> Gtk.Box:
    """Create a colored circle widget for tag display."""
    hex_color = COLOR_MAP.get(color_name, '#6e7781')
    circle = Gtk.Box(
        width_request=size, height_request=size,
        halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
    )
    css = Gtk.CssProvider()
    css.load_from_string(
        f'box {{ background: {hex_color}; border-radius: 50%;'
        f' min-width: {size}px; min-height: {size}px;'
        f' border: 1.5px solid alpha(white, 0.25); }}'
    )
    circle.get_style_context().add_provider(
        css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
    return circle


_TAG_CARD_CSS = (
    '.tag-card-emoji-bg { font-size: 140px;'
    ' opacity: 0.35; filter: blur(20px);'
    ' margin: -30px; }'
    ' .tag-card-bg-emoji { background: alpha(@accent_bg_color, 0.12);'
    '   border-radius: 12px; }'
    ' .tag-card-icon { font-size: 36px; }'
    ' .tag-card-color-circle { min-width: 36px; min-height: 36px;'
    '   border-radius: 50%;'
    '   border: 1.5px solid alpha(white, 0.25); }'
    ' .tag-card-rounded { border-radius: 12px; }'
)


@Gtk.Template(resource_path='/net/armatik/Kitsune/tag_card.ui')
class TagCard(Gtk.FlowBoxChild):
    __gtype_name__ = 'KitsuneTagCard'

    card_overlay = Gtk.Template.Child()
    card_bg = Gtk.Template.Child()
    icon_label = Gtk.Template.Child()
    count_label = Gtk.Template.Child()
    title_label = Gtk.Template.Child()

    def __init__(self, tag: dict, **kwargs):
        super().__init__(**kwargs)
        register_css(_TAG_CARD_CSS)
        self.tag = tag
        self.card_overlay.add_css_class('tag-card-rounded')

        self.title_label.set_label(tag['name'])
        release_count = len(tag.get('releases', []))
        if release_count > 0:
            self.count_label.set_label(f'{release_count}')
        else:
            self.count_label.set_visible(False)

        if tag['icon_type'] == 'emoji':
            self._setup_emoji(tag['icon_value'])
        else:
            self._setup_color(tag['icon_value'])

    def _setup_emoji(self, emoji: str):
        self.icon_label.set_label(emoji)
        self.icon_label.add_css_class('tag-card-icon')
        self.card_bg.add_css_class('tag-card-bg-emoji')

        bg_label = Gtk.Label(
            label=emoji, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
            hexpand=True,
            css_classes=['tag-card-emoji-bg'],
            can_target=False,
        )
        self.card_bg.set_baseline_position(Gtk.BaselinePosition.CENTER)
        bg_label.set_valign(Gtk.Align.FILL)
        self.card_bg.append(bg_label)

    def _setup_color(self, color_name: str):
        hex_color = COLOR_MAP.get(color_name, '#6e7781')

        circle = Gtk.Box(
            halign=Gtk.Align.CENTER,
            css_classes=['tag-card-color-circle'],
        )
        css = Gtk.CssProvider()
        css.load_from_string(
            f'.tag-card-color-circle {{ background: {hex_color}; }}'
        )
        circle.get_style_context().add_provider(
            css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        self.icon_label.set_visible(False)
        parent = self.icon_label.get_parent()
        parent.prepend(circle)

        bg_css = Gtk.CssProvider()
        bg_css.load_from_string(
            f'.tag-card-bg-colored {{'
            f' background-color: alpha({hex_color}, 0.4);'
            f' background-image:'
            f'   radial-gradient(circle at center,'
            f'     alpha(white, 0.18) 0%,'
            f'     alpha(white, 0.06) 35%,'
            f'     transparent 60%);'
            f' border-radius: 12px; }}'
        )
        self.card_bg.add_css_class('tag-card-bg-colored')
        self.card_bg.get_style_context().add_provider(
            bg_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
