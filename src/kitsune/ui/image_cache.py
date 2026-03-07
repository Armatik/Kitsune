# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import hashlib
import os

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Soup', '3.0')

from gi.repository import Gdk, Gio, GLib, Soup

_session = Soup.Session()
_cache_dir = os.path.join(GLib.get_user_cache_dir(), 'kitsune', 'posters')
_memory_cache: dict[str, Gdk.Texture] = {}


def _ensure_cache_dir():
    os.makedirs(_cache_dir, exist_ok=True)


def _url_to_path(url: str) -> str:
    ext = '.jpg'
    if '.avif' in url:
        ext = '.avif'
    elif '.png' in url:
        ext = '.png'
    elif '.webp' in url:
        ext = '.webp'
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    return os.path.join(_cache_dir, url_hash + ext)


def load_image(url: str, callback):
    """Load image from cache or network. callback(texture, error)."""
    if url in _memory_cache:
        callback(_memory_cache[url], None)
        return

    cache_path = _url_to_path(url)
    if os.path.exists(cache_path):
        try:
            texture = Gdk.Texture.new_from_filename(cache_path)
            _memory_cache[url] = texture
            callback(texture, None)
            return
        except Exception:
            os.remove(cache_path)

    msg = Soup.Message.new('GET', url)
    _session.send_and_read_async(
        msg, GLib.PRIORITY_DEFAULT, None,
        _on_downloaded, (url, cache_path, callback),
    )


def get_cache_size() -> int:
    """Return total size of disk cache in bytes."""
    total = 0
    if os.path.isdir(_cache_dir):
        for entry in os.scandir(_cache_dir):
            if entry.is_file():
                total += entry.stat().st_size
    return total


def clear_cache():
    """Remove all cached images from disk and memory."""
    _memory_cache.clear()
    if os.path.isdir(_cache_dir):
        for entry in os.scandir(_cache_dir):
            if entry.is_file():
                os.remove(entry.path)


def _on_downloaded(session, result, user_data):
    url, cache_path, callback = user_data
    try:
        gbytes = session.send_and_read_finish(result)
        data = gbytes.get_data()

        _ensure_cache_dir()
        with open(cache_path, 'wb') as f:
            f.write(data)

        texture = Gdk.Texture.new_from_bytes(gbytes)
        _memory_cache[url] = texture
        callback(texture, None)
    except Exception as e:
        callback(None, str(e))
