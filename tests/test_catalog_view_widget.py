# SPDX-License-Identifier: GPL-3.0-or-later

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from kitsune.ui.catalog_view import CatalogView


def test_narrow_propagates_to_grid(mock_client):
    view = CatalogView(client=mock_client)
    view.set_narrow(True)
    assert view._grid.flowbox.get_min_children_per_line() == 1
    assert view._grid.flowbox.get_max_children_per_line() == 1
    view.set_narrow(False)
    assert view._grid.flowbox.get_min_children_per_line() == 2


def test_release_activated_callback_stored(mock_client):
    view = CatalogView(client=mock_client)
    cb = lambda r: None
    view.set_on_release_activated(cb)
    assert view._on_release_activated is cb


def test_initial_page_state(mock_client):
    view = CatalogView(client=mock_client)
    # _load_next_page increments _page to 1 on init
    assert view._page == 1
    assert view._last_page == 1


def test_reset_catalog_clears_state(mock_client):
    view = CatalogView(client=mock_client)
    view._page = 3
    view._reached_end = True
    view._reset_catalog()
    assert view._page == 0
    assert view._last_page == 1
    assert view._loading is False
    assert view._reached_end is False


def test_large_window_open_prefetches_beyond_fallback_page():
    """Window opens huge (fullscreen-like): page 1 is sized by the
    pre-allocation fallback (12 items ≈ 2 rows), then the resize-aware
    prefetch must keep loading until the grid covers the viewport —
    otherwise the user is stuck at two rows with nothing to scroll."""
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk, GLib
    from kitsune.models.catalog import CatalogResponse, PaginationMeta
    from kitsune.models.release import Release, ReleaseName

    class FakeClient:
        def __init__(self):
            self.pages = []

        def get_catalog(self, page, limit, filters=None, callback=None,
                        cancellable=None):
            self.pages.append(page)
            releases = [
                Release(id=page * 1000 + i,
                        name=ReleaseName(main=f'R{page}-{i}',
                                         english=None, alternative=None),
                        alias=f'r{page}-{i}', type='TV', year=2024)
                for i in range(limit)
            ]
            callback(CatalogResponse(
                releases=releases,
                meta=PaginationMeta(current_page=page, last_page=50,
                                    total=10000)), None)

        def __getattr__(self, name):
            return lambda *a, **k: None

    client = FakeClient()
    view = CatalogView(client=client)
    win = Gtk.Window()
    win.set_child(view)
    win.set_default_size(1920, 1080)
    win.present()

    ctx = GLib.MainContext.default()
    for _ in range(400):
        if not ctx.iteration(False):
            break

    assert client.pages != [1], (
        f'prefetch stalled after fallback page (pages={client.pages})')
    assert view._page > 1
