# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gtk

from kitsune import tags_store
from kitsune.ui.widgets.tag_card import COLOR_MAP


def show_create_tag_dialog(parent, callback=None):
    """Show a dialog to create a new tag. Calls callback(tag_dict) or callback(None)."""
    dialog = Adw.AlertDialog(heading=_('New Tag'))
    dialog.add_response('cancel', _('Cancel'))
    dialog.add_response('create', _('Create'))
    dialog.set_response_appearance('create', Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response('create')
    dialog.set_close_response('cancel')

    content = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=16, margin_start=24, margin_end=24,
    )

    # Name entry
    name_row = Adw.EntryRow(title=_('Tag name'))
    name_group = Adw.PreferencesGroup()
    name_group.add(name_row)
    content.append(name_group)

    # Type toggle
    type_box = Gtk.Box(
        halign=Gtk.Align.CENTER, spacing=0,
        css_classes=['linked'],
    )
    emoji_btn = Gtk.ToggleButton(label=_('Emoji'), active=True)
    color_btn = Gtk.ToggleButton(label=_('Color'), group=emoji_btn)
    type_box.append(emoji_btn)
    type_box.append(color_btn)
    content.append(type_box)

    state = {'icon_type': 'emoji', 'icon_value': '⭐'}

    # Emoji picker area
    emoji_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL, spacing=8,
    )
    emoji_chooser_btn = Gtk.MenuButton(
        label='⭐', halign=Gtk.Align.CENTER,
    )
    chooser = Gtk.EmojiChooser()
    emoji_chooser_btn.set_popover(chooser)

    def on_emoji_picked(_chooser, emoji):
        state['icon_value'] = emoji
        emoji_chooser_btn.set_label(emoji)

    chooser.connect('emoji-picked', on_emoji_picked)
    emoji_box.append(Gtk.Label(
        label=_('Choose emoji:'),
        xalign=0, css_classes=['dim-label', 'caption'],
    ))
    emoji_box.append(emoji_chooser_btn)
    content.append(emoji_box)

    # Color picker area
    color_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL, spacing=8,
        visible=False,
    )
    color_box.append(Gtk.Label(
        label=_('Choose color:'),
        xalign=0, css_classes=['dim-label', 'caption'],
    ))
    color_flow = Gtk.FlowBox(
        selection_mode=Gtk.SelectionMode.SINGLE,
        max_children_per_line=5,
        min_children_per_line=5,
        homogeneous=True,
        column_spacing=8, row_spacing=8,
        halign=Gtk.Align.CENTER,
    )

    for color_name, hex_val in COLOR_MAP.items():
        circle = Gtk.Box(
            width_request=36, height_request=36,
            halign=Gtk.Align.CENTER,
        )
        css = Gtk.CssProvider()
        css.load_from_string(
            f'box {{ background: {hex_val}; border-radius: 50%;'
            f' min-width: 36px; min-height: 36px; }}'
        )
        circle.get_style_context().add_provider(
            css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        child = Gtk.FlowBoxChild()
        child.set_child(circle)
        child._color_name = color_name
        color_flow.append(child)

    def on_color_selected(_flow, child):
        state['icon_value'] = child._color_name

    color_flow.connect('child-activated', on_color_selected)
    color_flow.select_child(color_flow.get_child_at_index(0))

    color_box.append(color_flow)
    content.append(color_box)

    def on_type_toggled(_btn):
        if emoji_btn.get_active():
            state['icon_type'] = 'emoji'
            state['icon_value'] = '⭐'
            emoji_box.set_visible(True)
            color_box.set_visible(False)
        else:
            state['icon_type'] = 'color'
            state['icon_value'] = 'blue'
            emoji_box.set_visible(False)
            color_box.set_visible(True)

    emoji_btn.connect('toggled', on_type_toggled)

    dialog.set_extra_child(content)

    def on_response(_dialog, response):
        if response == 'create':
            name = name_row.get_text().strip()
            if name:
                tag = tags_store.create_tag(
                    name, state['icon_type'], state['icon_value'],
                )
                if callback:
                    callback(tag)
                return
        if callback:
            callback(None)

    dialog.connect('response', on_response)
    dialog.present(parent)
