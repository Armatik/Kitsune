# TODO

## Migration: Gtk.FlowBox → Gtk.GridView

Move grid-based release / genre / franchise / tag views from
`Gtk.FlowBox` (eager rendering of every child) to `Gtk.GridView`
(virtualised, backed by `Gio.ListModel`).

### Affected files

- `src/kitsune/ui/widgets/release_card.{py,blp}`
- `src/kitsune/ui/widgets/genre_card.{py,blp}`
- `src/kitsune/ui/widgets/franchise_card.{py,blp}`
- `src/kitsune/ui/widgets/tag_card.{py,blp}`
- `src/kitsune/ui/widgets/content_grid.{py,blp}`
- `src/kitsune/ui/catalog_view.py`
- `src/kitsune/ui/genres_view.py`, `franchises_view.py`, `tags_view.py`
- `src/kitsune/ui/{genre,franchise,tag}_releases_view.py`
- `src/kitsune/window.py` — `_refresh_visible_cards` walks flowbox
  children directly; switch to model-item update + factory rebind.
- Widget tests: rewrite or recreate.

### Why we deferred

Current scale is small (catalog page is 12–30 items, sub-views tens
not thousands). FlowBox memory footprint is acceptable; pull-refresh,
adult-blur and tag-badge refresh are already wired to it. Benefit is
marginal for today's users; cost is significant (~1.5–2 weeks).

### When to revisit

- If user-facing lists routinely exceed 500 items (watch history,
  large collections).
- If GNOME shifts FlowBox to deprecated status.
- If we hit a UX problem that virtualisation specifically solves
  (scroll jank on slower hardware, memory pressure on phones).

### Migration sketch

1. Define a per-card `Gtk.SignalListItemFactory`: setup-bind-unbind-teardown.
2. Replace `flowbox.append_child(Card(item))` with `liststore.append(item)`.
3. Translate `min/max-children-per-line` → GridView `min/max-columns`.
4. Rebuild CSS — `flowbox > flowboxchild` selectors become `gridview > child`.
5. Move `Adw.Clamp` to wrap GridView's own ScrolledWindow output,
   verify adaptive layout.
6. Re-wire `edge-overshot` (pull-refresh) and `EventControllerScroll`
   (source-device filter) on the right inner ScrolledWindow.
7. Replace per-card `refresh_tag_badges()` / `refresh_adult_blur()` with
   model-item-update + factory rebind.
8. Migrate widget tests one by one.
