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


_ADULT_BLUR_CSS = '.adult-blur { filter: blur(10px); }'


def apply_adult_blur(picture_widget, is_adult: bool) -> None:
    """Apply the 18+ blur CSS class to a Gtk.Picture iff the release is
    marked adult and the global confirmation hasn't been dismissed.

    The CSS filter blooms beyond widget bounds — the caller MUST host
    the picture inside a clipping container (Gtk.Overflow.HIDDEN on a
    rounded parent) or the blur will leak past the visible image edge.
    """
    if not is_adult:
        return
    register_css(_ADULT_BLUR_CSS)
    try:
        from gi.repository import Gio
        settings = Gio.Settings(schema_id='net.armatik.Kitsune')
        if settings.get_boolean('adult-warning-disabled'):
            return
    except Exception:
        pass
    picture_widget.add_css_class('adult-blur')


def format_size(size_bytes: int) -> str:
    """Format byte count as human-readable string (B/KB/MB/GB)."""
    if size_bytes < 1024:
        return f'{size_bytes} B'
    if size_bytes < 1024 * 1024:
        return f'{size_bytes / 1024:.1f} KB'
    if size_bytes < 1024 * 1024 * 1024:
        return f'{size_bytes / (1024 * 1024):.1f} MB'
    return f'{size_bytes / (1024 * 1024 * 1024):.1f} GB'
