# Kitsune

GNOME anime client for AniLibria API. Python 3.13 + GTK4 + Libadwaita 1.8 + GStreamer 1.28 + Soup3.

App ID: `net.armatik.Kitsune`, License: GPL-3.0-or-later

## Commands

```bash
# Build & install
meson setup _build -Dprefix=$HOME/.local
meson compile -C _build
meson install -C _build

# Tests (19 Meson tests: 7 non-GUI + 9 widget via xvfb-run + 3 validation)
meson test -C _build

# i18n (ONLY through Meson, never xgettext directly)
meson compile -C _build kitsune-pot/kitsune-update-po

# Clean rebuild
rm -rf _build && meson setup _build && meson compile -C _build
```

## Architecture

```
src/kitsune/
├── api/client.py          # Soup3 async HTTP (callback pattern, not asyncio)
├── models/                # Dataclasses with from_dict() parsing
│   ├── release.py         # Release, Episode, Genre, Member, Torrent
│   ├── catalog.py         # CatalogResponse, PaginationMeta
│   └── franchise.py       # Franchise
├── player/gst_player.py   # GStreamer playbin3 + gtk4paintablesink
├── storage/               # JSON files in XDG dirs, atomic writes
│   ├── release_cache.py   # ~/.cache/kitsune/releases/
│   ├── tags_store.py      # ~/.local/share/kitsune/tags.json
│   └── watch_positions.py # ~/.local/share/kitsune/watch_positions.json
└── ui/
    ├── *_view.py           # Views (catalog, search, release, player, genres, franchises, tags)
    ├── *.blp               # Blueprint UI definitions (6 files)
    └── widgets/            # Reusable widgets (content_grid, release_card, genre_card, franchise_card, tag_card)
        └── *.blp           # Blueprint widget definitions (5 files)
```

## Key Patterns

- **Async HTTP**: Soup3 callback `(data, error)` via GLib event loop — no asyncio, no threads
- **UI Templates**: `.blp` → `.ui` (blueprint-compiler) → `.gresource` (glib-compile-resources)
  - Two `custom_target` needed for ui/ and ui/widgets/ directories
  - `install_subdir` must `exclude_files` all `.blp` files
- **Models**: Dataclasses with `from_dict(cls, data)` factory, safe `.get()` defaults
- **Storage**: Atomic JSON writes (mkstemp → write → close → replace)
- **Navigation**: Adw.NavigationView, push/pop pages, Adw.MultiLayoutView for adaptive layout
- **Widget binding**: `@Gtk.Template(resource_path=...)` + `Gtk.Template.Child()`

## Sync subsystem

Bidirectional sync with the AniLibria account (favorites, 5 built-in collections,
watch positions) is organized around a persistent operation queue. Every local
write (star a release, mark an episode as watched, etc.) is enqueued in
`PendingQueue` and then drained asynchronously to the server:

- `src/kitsune/storage/pending_queue.py` — persistent FIFO queue (`~/.local/share/kitsune/pending_ops.json`) with coalescing, exponential backoff retry `[10, 30, 60, 120, 300, 600]`, and in-memory in-flight tracking.
- `src/kitsune/storage/sync_manager.py` — `SyncManager` routes write-through through the queue, drains via `GLib.idle_add`, batches save_timecode ops (up to 50 per HTTP call), reacts to `session-expired` (pause) / `session-restored` (resume) / `logged-out` (clear queue).
- `src/kitsune/storage/watch_positions.py` — v2 schema `{version, entries: {key: {pos, episode_id, updated_at}}}` with lazy v1 migration. `apply_server_entry` does conflict resolution (local wins on tie).
- `src/kitsune/storage/episode_index.py` — reverse index `episode_id → (release_id, ordinal)`, populated opportunistically by `release_cache.save`, used as fallback for pulled timecodes.
- `src/kitsune/auth/session.py` — `SessionManager` has `is_expired()` / `clear_expired()` / `force_logout_cleanup()`; 401 from server flips `_expired=True`. `logout()` wipes all synced local data before the server POST.
- Session-expired banner — inline `Adw.Banner` in `window.blp` next to `offline_banner`; revealed by `session-expired`, hidden by `session-restored` / `logged-out`. `button-clicked` → `on_session_banner_login` in `window.py` opens the auth dialog.
- `src/kitsune/ui/profile_view.py` — pending-ops indicator with retry-now button, subscribed to `queue-changed` / `sync-complete`.

Pub/sub everywhere uses the callback-list pattern (`connect_*` methods storing callables in a list), NOT GObject signals.

For the full architecture + stage-by-stage history see
`docs/superpowers/specs/2026-04-12-sync-overhaul-design.md`.

## Gotchas

- `Adw.LayoutSlot` uses GtkWidget `id` property, NOT `slot-name`
- Blueprint `output: '.'` breaks because `configure_file` creates `_build/src/kitsune` as a file
- Built-in "Избранное" tag has hardcoded `id='favorites'`, `builtin=True`
- Watch position `-1` means fully watched; position `<= 5` is removed from storage
- GResource path: `/net/armatik/Kitsune/window.ui` (widgets same level, no widgets/ prefix)
- Widget tests must run `is_parallel: false` (GTK not thread-safe)

## Testing

- **Non-GUI** (5): test_models, test_navbar, test_storage, test_tags_store, test_watch_positions — fast, no display
- **Widget** (8): test_content_grid, test_catalog_view, test_genres_view, test_release_card, test_tag_card, test_release_view, test_tags_view, test_player_view — need xvfb-run
- Fixtures in `conftest.py`: `mock_client` (StubClient), `mock_tags`, `mock_cache`, `sample_release`, `sample_genre`, `sample_tag`

## Code Style

- Python, no type annotations enforced
- Strings: `_()` for i18n (gettext via builtins)
- GSettings for all user preferences
- No ORM, no pip dependencies — everything through system PyGObject
