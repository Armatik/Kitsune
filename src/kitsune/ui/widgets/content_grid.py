# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gtk

_SCROLL_UP_THRESHOLD = 600
_SCROLL_NEAR_END_OFFSET = 200


class ContentGrid(Gtk.Box):
    """Reusable scrollable FlowBox grid with scroll-to-top, spinner, and end label."""

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self._on_scroll_near_end = None
        self._on_child_activated = None
        self._build_ui()

    @property
    def flowbox(self):
        return self._flowbox

    def set_narrow(self, narrow: bool):
        if narrow:
            self._flowbox.set_min_children_per_line(1)
            self._flowbox.set_max_children_per_line(1)
        else:
            self._flowbox.set_min_children_per_line(2)
            self._flowbox.set_max_children_per_line(6)

    def set_on_scroll_near_end(self, callback):
        self._on_scroll_near_end = callback

    def set_on_child_activated(self, callback):
        self._on_child_activated = callback

    def set_spinner_visible(self, visible: bool):
        self._spinner.set_visible(visible)

    def show_end(self):
        self._spinner.set_visible(False)
        self._end_label.set_visible(True)

    def clear(self):
        self._end_label.set_visible(False)
        while child := self._flowbox.get_first_child():
            self._flowbox.remove(child)
        self._vadjustment.set_value(0)

    def append_child(self, widget):
        self._flowbox.append(widget)

    def _build_ui(self):
        overlay = Gtk.Overlay(vexpand=True)

        self._scrolled = Gtk.ScrolledWindow(vexpand=True)
        self._scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._vadjustment = self._scrolled.get_vadjustment()
        self._vadjustment.connect('value-changed', self._on_scroll)

        self._flowbox = Gtk.FlowBox(
            homogeneous=True,
            min_children_per_line=2,
            max_children_per_line=6,
            column_spacing=12,
            row_spacing=12,
            margin_start=12,
            margin_end=12,
            margin_top=12,
            margin_bottom=12,
            selection_mode=Gtk.SelectionMode.NONE,
            activate_on_single_click=True,
        )
        self._flowbox.connect('child-activated', self._on_activated)

        self._spinner = Adw.Spinner(margin_top=24, margin_bottom=24)
        self._spinner.set_halign(Gtk.Align.CENTER)

        self._end_label = Gtk.Label(
            label=_('That\'s all!'),
            margin_top=24,
            margin_bottom=24,
            css_classes=['dim-label', 'title-3'],
        )
        self._end_label.set_visible(False)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_box.append(self._flowbox)
        content_box.append(self._spinner)
        content_box.append(self._end_label)

        self._scrolled.set_child(content_box)
        overlay.set_child(self._scrolled)

        # Scroll-to-top button
        scroll_up_btn = Gtk.Button(
            icon_name='go-up-symbolic',
            tooltip_text=_('Scroll to top'),
            css_classes=['circular', 'osd'],
        )
        scroll_up_btn.connect('clicked', self._on_scroll_up)

        self._scroll_up_revealer = Gtk.Revealer(
            transition_type=Gtk.RevealerTransitionType.CROSSFADE,
            transition_duration=300,
            reveal_child=False,
            halign=Gtk.Align.END,
            valign=Gtk.Align.END,
            margin_end=18,
            margin_bottom=18,
        )
        self._scroll_up_revealer.set_child(scroll_up_btn)
        overlay.add_overlay(self._scroll_up_revealer)

        self.append(overlay)

    def _on_scroll(self, adjustment):
        value = adjustment.get_value()
        self._scroll_up_revealer.set_reveal_child(value > _SCROLL_UP_THRESHOLD)

        if self._on_scroll_near_end:
            upper = adjustment.get_upper()
            page_size = adjustment.get_page_size()
            if value + page_size >= upper - _SCROLL_NEAR_END_OFFSET:
                self._on_scroll_near_end()

    def _on_scroll_up(self, _button):
        self._vadjustment.set_value(0)

    def _on_activated(self, _flowbox, child):
        if self._on_child_activated:
            self._on_child_activated(child)
