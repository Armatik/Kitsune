# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')

from gi.repository import Gdk, Gtk

_registered_css = set()


def register_css(css_string: str):
    """Register a CSS string globally, skipping if already registered."""
    key = id(css_string)
    if key in _registered_css:
        return
    _registered_css.add(key)
    provider = Gtk.CssProvider()
    provider.load_from_string(css_string)
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


def format_size(size_bytes: int) -> str:
    """Format byte count as human-readable string (B/KB/MB/GB)."""
    if size_bytes < 1024:
        return f'{size_bytes} B'
    if size_bytes < 1024 * 1024:
        return f'{size_bytes / 1024:.1f} KB'
    if size_bytes < 1024 * 1024 * 1024:
        return f'{size_bytes / (1024 * 1024):.1f} MB'
    return f'{size_bytes / (1024 * 1024 * 1024):.1f} GB'
