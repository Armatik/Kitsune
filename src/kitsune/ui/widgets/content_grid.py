# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gtk

_SCROLL_UP_THRESHOLD = 600
_SCROLL_NEAR_END_OFFSET = 200


@Gtk.Template(resource_path='/net/armatik/Kitsune/content_grid.ui')
class ContentGrid(Gtk.Box):
    """Reusable scrollable FlowBox grid with scroll-to-top, spinner, and end label."""
    __gtype_name__ = 'KitsuneContentGrid'

    scrolled = Gtk.Template.Child()
    flowbox = Gtk.Template.Child()
    spinner = Gtk.Template.Child()
    end_label = Gtk.Template.Child()
    scroll_up_revealer = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._on_scroll_near_end = None
        self._on_child_activated = None
        self._vadjustment = self.scrolled.get_vadjustment()
        self._vadjustment.connect('value-changed', self._on_scroll)

    def set_narrow(self, narrow: bool):
        if narrow:
            self.flowbox.set_min_children_per_line(1)
            self.flowbox.set_max_children_per_line(1)
        else:
            self.flowbox.set_min_children_per_line(2)
            self.flowbox.set_max_children_per_line(6)

    def set_on_scroll_near_end(self, callback):
        self._on_scroll_near_end = callback

    def set_on_child_activated(self, callback):
        self._on_child_activated = callback

    def set_spinner_visible(self, visible: bool):
        self.spinner.set_visible(visible)

    def show_end(self):
        self.spinner.set_visible(False)
        self.end_label.set_visible(True)

    def clear(self):
        self.end_label.set_visible(False)
        while child := self.flowbox.get_first_child():
            self.flowbox.remove(child)
        self._vadjustment.set_value(0)

    def append_child(self, widget):
        self.flowbox.append(widget)

    def _on_scroll(self, adjustment):
        value = adjustment.get_value()
        self.scroll_up_revealer.set_reveal_child(value > _SCROLL_UP_THRESHOLD)

        if self._on_scroll_near_end:
            upper = adjustment.get_upper()
            page_size = adjustment.get_page_size()
            if value + page_size >= upper - _SCROLL_NEAR_END_OFFSET:
                self._on_scroll_near_end()

    @Gtk.Template.Callback()
    def on_scroll_up(self, _button):
        self._vadjustment.set_value(0)

    @Gtk.Template.Callback()
    def on_activated(self, _flowbox, child):
        if self._on_child_activated:
            self._on_child_activated(child)
