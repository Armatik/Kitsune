# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import io
import logging
import random

import cairo

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('GdkPixbuf', '2.0')

from gi.repository import Gdk, GdkPixbuf, GLib, Gio

_log = logging.getLogger('kitsune.color_extractor')


def extract_colors(texture: Gdk.Texture, count: int = 6) -> list[tuple[int, int, int]]:
    """Extract dominant colors from a Gdk.Texture using median cut."""
    _log.debug('Extracting colors from texture %dx%d', texture.get_width(), texture.get_height())
    png_bytes = texture.save_to_png_bytes()
    stream = Gio.MemoryInputStream.new_from_bytes(png_bytes)
    pixbuf = GdkPixbuf.Pixbuf.new_from_stream(stream, None)
    small = pixbuf.scale_simple(32, 32, GdkPixbuf.InterpType.BILINEAR)

    pixels_data = small.get_pixels()
    n_channels = small.get_n_channels()
    rowstride = small.get_rowstride()
    w = small.get_width()
    h = small.get_height()
    _log.debug('Downscaled to %dx%d, channels=%d, rowstride=%d', w, h, n_channels, rowstride)

    pixels = []
    for y in range(h):
        for x in range(w):
            offset = y * rowstride + x * n_channels
            r, g, b = pixels_data[offset], pixels_data[offset + 1], pixels_data[offset + 2]
            if _is_interesting(r, g, b):
                pixels.append((r, g, b))

    _log.debug('Interesting pixels: %d / %d', len(pixels), w * h)

    if not pixels:
        _log.debug('No interesting pixels, returning fallback color')
        return [(80, 80, 120)]

    result = _median_cut(pixels, count)
    _log.debug('Median cut result: %s', result)
    return result


def create_gradient_texture(colors: list[tuple[int, int, int]], n_points: int = 3, size: int = 64) -> Gdk.Texture:
    """Create a small gradient image with colored blobs. Looks blurred when scaled up."""
    n_points = max(2, min(n_points, len(colors)))
    chosen = random.sample(colors, n_points)

    _log.debug('Creating gradient texture %dx%d with %d color points', size, size, len(chosen))

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    ctx = cairo.Context(surface)

    for r, g, b in chosen:
        cx = random.uniform(0.1, 0.9) * size
        cy = random.uniform(0.05, 0.55) * size
        radius = random.uniform(0.25, 0.5) * size
        alpha = random.uniform(0.6, 0.95)

        pattern = cairo.RadialGradient(cx, cy, 0, cx, cy, radius)
        pattern.add_color_stop_rgba(0, r / 255, g / 255, b / 255, alpha)
        pattern.add_color_stop_rgba(1, r / 255, g / 255, b / 255, 0.0)

        ctx.set_source(pattern)
        ctx.paint()

    buf = io.BytesIO()
    surface.write_to_png(buf)
    gbytes = GLib.Bytes.new(buf.getvalue())
    texture = Gdk.Texture.new_from_bytes(gbytes)

    _log.debug('Gradient texture created: %dx%d', texture.get_width(), texture.get_height())
    return texture


def _is_interesting(r: int, g: int, b: int) -> bool:
    brightness = (r + g + b) / 3
    if brightness < 20 or brightness > 240:
        return False
    saturation = max(r, g, b) - min(r, g, b)
    return saturation > 15


def _median_cut(pixels: list[tuple[int, int, int]], depth: int) -> list[tuple[int, int, int]]:
    if depth <= 1 or len(pixels) <= 1:
        r = sum(p[0] for p in pixels) // len(pixels)
        g = sum(p[1] for p in pixels) // len(pixels)
        b = sum(p[2] for p in pixels) // len(pixels)
        return [(r, g, b)]

    ranges = []
    for ch in range(3):
        vals = [p[ch] for p in pixels]
        ranges.append(max(vals) - min(vals))

    split_ch = ranges.index(max(ranges))
    pixels.sort(key=lambda p: p[split_ch])
    mid = len(pixels) // 2

    return _median_cut(pixels[:mid], depth // 2) + _median_cut(pixels[mid:], depth - depth // 2)
