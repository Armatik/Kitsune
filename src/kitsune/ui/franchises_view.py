# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from kitsune.ui.franchise_releases_view import FranchiseReleasesView
from kitsune.ui.items_grid_view import ItemsGridView
from kitsune.ui.widgets.franchise_card import FranchiseCard


class FranchisesView(ItemsGridView):

    @property
    def current_franchise_name(self) -> str:
        return self.current_item_name

    def _load_items(self):
        self._grid.set_spinner_visible(True)
        self._client.get_franchises(callback=self._on_items_loaded)

    def _create_card(self, item):
        return FranchiseCard(item)

    def _get_item_from_card(self, card):
        if isinstance(card, FranchiseCard):
            return card.franchise
        return None

    def _show_item_releases(self, item):
        releases_view = FranchiseReleasesView(
            franchise=item, client=self._client,
        )
        self._show_releases(item, releases_view)
