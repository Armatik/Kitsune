# SPDX-License-Identifier: GPL-3.0-or-later

import builtins
import gettext
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Install gettext _() builtin before any kitsune imports
builtins._ = gettext.gettext

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Gst', '1.0')

from gi.repository import Adw, Gio, Gst, Gtk

import pytest

# One-time GTK + Adw + GStreamer init
Adw.init()
Gst.init(None)

# Load compiled GResource bundle
_build_dir = os.path.join(os.path.dirname(__file__), '..', '_build', 'src')
_gresource = os.path.join(_build_dir, 'net.armatik.Kitsune.gresource')
if os.path.exists(_gresource):
    resource = Gio.Resource.load(_gresource)
    Gio.resources_register(resource)

from kitsune import tags_store
from kitsune import release_cache
from kitsune.storage import search_index


class StubClient:
    """Minimal AniLibriaClient stub — all methods accept callbacks but do nothing."""

    def get_catalog(self, **kwargs):
        pass

    def get_genres(self, **kwargs):
        pass

    def get_franchises(self, **kwargs):
        pass

    def get_release(self, *args, **kwargs):
        pass

    def get_release_raw(self, *args, **kwargs):
        pass

    def get_franchise_for_release(self, *args, **kwargs):
        pass

    def get_year_range(self, **kwargs):
        pass

    def search_releases(self, *args, **kwargs):
        pass

    def set_on_network_error(self, cb):
        pass

    def set_on_network_ok(self, cb):
        pass

    def set_token_getter(self, getter):
        pass

    def login(self, *args, **kwargs):
        pass

    def logout(self, **kwargs):
        pass

    def get_otp(self, *args, **kwargs):
        pass

    def login_otp(self, *args, **kwargs):
        pass

    def get_social_login_url(self, *args, **kwargs):
        pass

    def poll_social_auth(self, *args, **kwargs):
        pass

    def get_profile(self, **kwargs):
        pass

    def get_favorite_ids(self, **kwargs):
        pass

    def add_favorites(self, *args, **kwargs):
        pass

    def remove_favorites(self, *args, **kwargs):
        pass

    def get_collection_ids(self, **kwargs):
        pass

    def add_to_collection(self, *args, **kwargs):
        pass

    def remove_from_collection(self, *args, **kwargs):
        pass

    def get_timecodes(self, **kwargs):
        pass

    def save_timecodes(self, *args, **kwargs):
        pass


@pytest.fixture
def mock_client():
    return StubClient()


@pytest.fixture
def mock_tags(tmp_path):
    """Redirect tags_store to a temp file."""
    f = tmp_path / 'tags.json'
    original = tags_store._TAGS_FILE
    tags_store._TAGS_FILE = f
    yield f
    tags_store._TAGS_FILE = original


@pytest.fixture
def mock_cache(tmp_path):
    """Redirect release_cache to a temp directory."""
    d = tmp_path / 'releases'
    d.mkdir()
    original = release_cache._CACHE_DIR
    release_cache._CACHE_DIR = d
    yield d
    release_cache._CACHE_DIR = original


@pytest.fixture
def mock_index(tmp_path):
    """Redirect search_index to a temp file."""
    f = tmp_path / 'index.json'
    original = search_index._INDEX_FILE
    search_index._INDEX_FILE = f
    search_index._cache = None
    yield f
    search_index._INDEX_FILE = original
    search_index._cache = None


@pytest.fixture
def sample_release():
    from kitsune.models import Release
    return Release.from_dict({
        'id': 42,
        'name': {'main': 'Test Release', 'english': 'Test EN', 'alternative': ''},
        'alias': 'test-release',
        'description': 'A test release.',
        'poster': None,
        'type': {'value': 'TV', 'description': 'TV'},
        'year': 2025,
        'season': {'value': 'winter', 'description': 'Winter'},
        'age_rating': {'value': 'R12_PLUS', 'label': '12+'},
        'episodes_total': 12,
        'is_ongoing': False,
        'genres': [],
        'episodes': [],
        'members': [],
        'torrents': [],
    })


@pytest.fixture
def sample_genre():
    from kitsune.models.release import Genre
    return Genre(id=1, name='Action', image=None, total_releases=50)


@pytest.fixture
def sample_tag():
    return {
        'id': 'abc12345',
        'name': 'Top',
        'icon_type': 'emoji',
        'icon_value': '🔥',
        'builtin': False,
        'order': 1,
        'releases': [42, 43],
    }
