# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import hashlib
import logging
import os
from collections import OrderedDict
from urllib.parse import urlparse

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Soup', '3.0')

from gi.repository import Gdk, Gio, GLib, Soup

log = logging.getLogger('kitsune.image_cache')

_session = Soup.Session()
_base_cache_dir = os.path.join(GLib.get_user_cache_dir(), 'kitsune')
_MAX_MEMORY_CACHE = 300
_MAX_DOWNLOAD_SIZE = 30 * 1024 * 1024  # 30 MB
_memory_cache: OrderedDict[str, Gdk.Texture] = OrderedDict()


def get_from_memory(url: str):
    """Return cached Gdk.Texture if url is in memory, else None."""
    return _memory_cache.get(url)


def _cache_dir(category: str = 'posters') -> str:
    return os.path.join(_base_cache_dir, category)


def _ensure_cache_dir(category: str = 'posters'):
    os.makedirs(_cache_dir(category), exist_ok=True)


_ALLOWED_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.avif'}


def _url_to_path(url: str, category: str = 'posters') -> str:
    parsed = urlparse(url)
    _, ext = os.path.splitext(parsed.path)
    ext = ext.lower()
    if ext not in _ALLOWED_EXTS:
        ext = '.jpg'
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    return os.path.join(_cache_dir(category), url_hash + ext)


def load_image(url: str, callback, category: str = 'posters'):
    """Load image from cache or network. callback(texture, error)."""
    if url in _memory_cache:
        log.debug('memory hit: %s [%s]', url, category)
        _memory_cache.move_to_end(url)
        callback(_memory_cache[url], None)
        return

    cache_path = _url_to_path(url, category)
    if os.path.exists(cache_path):
        try:
            texture = Gdk.Texture.new_from_filename(cache_path)
            _memory_cache[url] = texture
            log.debug('disk hit: %s [%s]', url, category)
            callback(texture, None)
            return
        except (GLib.Error, OSError, ValueError):
            log.debug('disk corrupted, removing: %s', cache_path)
            os.remove(cache_path)

    log.debug('download: %s [%s]', url, category)
    msg = Soup.Message.new('GET', url)
    _session.send_and_read_async(
        msg, GLib.PRIORITY_DEFAULT, None,
        _on_downloaded, (url, cache_path, callback, category),
    )


def get_cache_size(category: str = 'posters') -> int:
    """Return total size of disk cache in bytes."""
    total = 0
    d = _cache_dir(category)
    if os.path.isdir(d):
        for entry in os.scandir(d):
            if entry.is_file():
                total += entry.stat().st_size
    return total


def get_cache_count(category: str = 'posters') -> int:
    """Return number of cached files."""
    d = _cache_dir(category)
    if not os.path.isdir(d):
        return 0
    return sum(1 for e in os.scandir(d) if e.is_file())


def clear_cache(category: str = 'posters'):
    """Remove cached images from disk and memory for given category."""
    d = _cache_dir(category)
    removed = 0
    if os.path.isdir(d):
        for entry in os.scandir(d):
            if entry.is_file():
                os.remove(entry.path)
                removed += 1
    # Clear memory entries whose disk path matched this category
    to_remove = [
        url for url in _memory_cache
        if _url_to_path(url, category).startswith(d)
    ]
    for url in to_remove:
        del _memory_cache[url]
    log.debug('cleared %d files from %s', removed, category)


def _on_downloaded(session, result, user_data):
    url, cache_path, callback, category = user_data
    try:
        gbytes = session.send_and_read_finish(result)
        data = gbytes.get_data()

        if len(data) > _MAX_DOWNLOAD_SIZE:
            log.debug('download too large (%d bytes): %s', len(data), url)
            callback(None, 'Image too large')
            return

        texture = Gdk.Texture.new_from_bytes(gbytes)

        _ensure_cache_dir(category)
        with open(cache_path, 'wb') as f:
            f.write(data)

        _memory_cache[url] = texture
        while len(_memory_cache) > _MAX_MEMORY_CACHE:
            _memory_cache.popitem(last=False)
        log.debug('cached: %s (%d bytes) [%s]', url, len(data), category)
        callback(texture, None)
    except (GLib.Error, OSError, ValueError) as e:
        log.debug('download failed: %s — %s', url, e)
        callback(None, str(e))
