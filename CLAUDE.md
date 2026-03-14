# Kitsune

GNOME anime client for AniLibria API. Python 3.13 + GTK4 + Libadwaita 1.8 + GStreamer 1.28 + Soup3.

App ID: `net.armatik.Kitsune`, License: GPL-3.0-or-later

## Commands

```bash
# Build & install
meson setup _build -Dprefix=$HOME/.local
meson compile -C _build
meson install -C _build

# Tests (13 Meson tests: 5 non-GUI + 8 widget via xvfb-run)
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
