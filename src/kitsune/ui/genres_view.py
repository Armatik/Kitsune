# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from kitsune.ui.genre_releases_view import GenreReleasesView
from kitsune.ui.items_grid_view import ItemsGridView
from kitsune.ui.widgets.genre_card import GenreCard


class GenresView(ItemsGridView):

    @property
    def current_genre_name(self) -> str:
        return self.current_item_name

    def _load_items(self):
        self._grid.set_spinner_visible(True)
        self._client.get_genres(callback=self._on_items_loaded)

    def _create_card(self, item):
        return GenreCard(item)

    def _get_item_from_card(self, card):
        if isinstance(card, GenreCard):
            return card.genre
        return None

    def _show_item_releases(self, item):
        releases_view = GenreReleasesView(
            genre=item, client=self._client,
        )
        self._show_releases(item, releases_view)
