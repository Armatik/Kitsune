# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from kitsune.api import AniLibriaClient
from kitsune.storage import search_index, tags_store, watch_positions, release_cache
from kitsune.models import Release
from kitsune.models.release import Genre, ReleaseName
from kitsune.models.franchise import Franchise
from kitsune.ui import register_css

_SEARCH_CSS = (
    '.search-tab { padding: 4px 10px; min-height: 0; min-width: 0;'
    ' font-size: 12px; border-radius: 99px; }'
    ' .search-tab:checked { background: @accent_bg_color;'
    ' color: @accent_fg_color; }'
    ' .search-result-row { border-radius: 12px;'
    ' padding: 10px; margin: 3px 6px; }'
    ' .search-poster { border-radius: 8px; }'
    ' .search-section-header { margin: 8px 12px 2px; }'
)


def _categories():
    return [
        ('anime', _('Anime')),
        ('genres', _('Genres')),
        ('franchises', _('Franchises')),
        ('tags', _('Tags')),
    ]


@Gtk.Template(resource_path='/net/armatik/Kitsune/search_dialog.ui')
class SearchDialog(Adw.Dialog):
    __gtype_name__ = 'KitsuneSearchDialog'

    search_entry = Gtk.Template.Child()
    tabs_box = Gtk.Template.Child()
    stack = Gtk.Template.Child()
    scrolled = Gtk.Template.Child()
    listbox = Gtk.Template.Child()
    empty_subtitle = Gtk.Template.Child()

    def __init__(self, client: AniLibriaClient, **kwargs):
        super().__init__(**kwargs)
        register_css(_SEARCH_CSS)
        self._client = client
        self._cancellable = None
        self._debounce_id = 0
        self._on_release_activated = None
        self._on_episode_play = None
        self._on_genre_activated = None
        self._on_franchise_activated = None
        self._on_tag_activated = None
        self._tab_buttons: dict[str, Gtk.ToggleButton] = {}
        self._section_indices: dict[str, int] = {}
        self._results: dict[str, list] = {}

        self.empty_subtitle.set_label(
            _('Search anime, genres, franchises and tags')
        )
        self._build_tabs()
        self._setup_keyboard()
        self.connect('closed', self._on_closed)
        self._ensure_index_populated()

    # --- Public setters ---

    def set_on_release_activated(self, cb):
        self._on_release_activated = cb

    def set_on_episode_play(self, cb):
        self._on_episode_play = cb

    def set_on_genre_activated(self, cb):
        self._on_genre_activated = cb

    def set_on_franchise_activated(self, cb):
        self._on_franchise_activated = cb

    def set_on_tag_activated(self, cb):
        self._on_tag_activated = cb

    # --- Preload index ---

    def _ensure_index_populated(self):
        """Load genres/franchises into index if not cached yet."""
        if search_index.get_genres() is None:
            self._client.get_genres(callback=self._on_preload_genres)
        if search_index.get_franchises() is None:
            self._client.get_franchises(callback=self._on_preload_franchises)

    def _on_preload_genres(self, genres, error):
        if not error and genres:
            search_index.update_genres(genres)

    def _on_preload_franchises(self, franchises, error):
        if not error and franchises:
            search_index.update_franchises(franchises)

    # --- Tabs ---

    def _build_tabs(self):
        for cat_id, label in _categories():
            btn = Gtk.ToggleButton(
                label=label,
                css_classes=['pill', 'search-tab'],
            )
            btn.connect('toggled', self._on_tab_toggled, cat_id)
            self.tabs_box.append(btn)
            self._tab_buttons[cat_id] = btn
            btn.set_visible(False)

    def _on_tab_toggled(self, btn, cat_id):
        if not btn.get_active():
            return
        for cid, b in self._tab_buttons.items():
            if cid != cat_id and b.get_active():
                b.set_active(False)
        idx = self._section_indices.get(cat_id)
        if idx is not None:
            row = self.listbox.get_row_at_index(idx)
            if row:
                row.grab_focus()

    def _update_tabs(self):
        for cat_id, btn in self._tab_buttons.items():
            btn.set_visible(bool(self._results.get(cat_id)))

    # --- Search ---

    @Gtk.Template.Callback()
    def on_search_changed(self, entry):
        if self._debounce_id:
            GLib.source_remove(self._debounce_id)
            self._debounce_id = 0

        query = entry.get_text().strip()
        if len(query) < 2:
            self.stack.set_visible_child_name('empty')
            self._clear_results()
            return

        self._do_local_search(query)
        self._render_results()
        self._debounce_id = GLib.timeout_add(300, self._do_api_search, query)

    def _do_local_search(self, query):
        self._results['anime'] = search_index.search_releases(query)
        self._results['genres'] = search_index.search_genres(query)
        self._results['franchises'] = search_index.search_franchises(query)

        all_tags = tags_store.get_all_tags()
        q = query.casefold()
        self._results['tags'] = [
            t for t in all_tags if q in t['name'].casefold()
        ]

    def _do_api_search(self, query):
        self._debounce_id = 0
        if getattr(self._client, '_offline', False):
            return GLib.SOURCE_REMOVE

        if self._cancellable:
            self._cancellable.cancel()
        self._cancellable = Gio.Cancellable()

        self._client.search_releases(
            query=query,
            callback=self._on_api_results,
            cancellable=self._cancellable,
        )
        return GLib.SOURCE_REMOVE

    def _on_api_results(self, releases, error):
        if error or not releases:
            return

        api_entries = []
        for release in releases:
            entry = {
                'id': release.id,
                'main': release.name.main,
                'english': release.name.english,
                'alternative': release.name.alternative,
                'description': release.description,
                'poster_preview': release.poster_preview,
                'type': release.type,
                'year': release.year,
                'is_ongoing': release.is_ongoing,
                'episodes_total': release.episodes_total,
                'genres': [g.id for g in release.genres],
            }
            api_entries.append(entry)

        api_ids = {e['id'] for e in api_entries}
        local_only = [
            r for r in self._results.get('anime', [])
            if r['id'] not in api_ids
        ]
        self._results['anime'] = api_entries + local_only
        self._render_results()

    def _clear_results(self):
        self._results = {}
        while row := self.listbox.get_first_child():
            self.listbox.remove(row)
        self._section_indices = {}
        self._update_tabs()

    # --- Rendering ---

    def _render_results(self):
        while row := self.listbox.get_first_child():
            self.listbox.remove(row)
        self._section_indices = {}

        total = 0
        idx = 0
        for cat_id, label in _categories():
            items = self._results.get(cat_id, [])
            if not items:
                continue
            header = self._make_section_header(label)
            self.listbox.append(header)
            self._section_indices[cat_id] = idx
            idx += 1
            for item in items:
                row = self._make_row(cat_id, item)
                self.listbox.append(row)
                idx += 1
                total += 1

        self._update_tabs()
        if total > 0:
            self.stack.set_visible_child_name('results')
        else:
            self.stack.set_visible_child_name('no-results')

    def _make_section_header(self, label):
        lbl = Gtk.Label(
            label=label, xalign=0,
            css_classes=['heading', 'dim-label', 'search-section-header'],
        )
        row = Gtk.ListBoxRow(child=lbl, activatable=False, selectable=False)
        row.set_can_focus(False)
        return row

    def _make_row(self, cat_id, item):
        if cat_id == 'anime':
            return self._make_anime_row(item)
        elif cat_id == 'genres':
            return self._make_genre_row(item)
        elif cat_id == 'franchises':
            return self._make_franchise_row(item)
        elif cat_id == 'tags':
            return self._make_tag_row(item)
        return Gtk.ListBoxRow()

    # --- Anime row ---

    def _make_anime_row(self, entry):
        box = Gtk.Box(spacing=12)
        box.add_css_class('search-result-row')

        # Poster — fixed size via Overlay with size constraints
        poster_overlay = Gtk.Overlay(
            width_request=56, height_request=80,
        )
        poster_overlay.set_size_request(56, 80)
        if entry.get('poster_preview'):
            from kitsune.ui.image_cache import load_image
            picture = Gtk.Picture(
                width_request=56, height_request=80,
                content_fit=Gtk.ContentFit.COVER,
            )
            picture.add_css_class('search-poster')
            picture.set_size_request(56, 80)
            load_image(entry['poster_preview'], lambda tex, err, p=picture:
                       p.set_paintable(tex) if tex else None, category='posters')
            poster_overlay.set_child(picture)
        else:
            placeholder = Gtk.Image(
                icon_name='net.armatik.Kitsune.image-missing-symbolic',
                pixel_size=24, opacity=0.3,
                width_request=56, height_request=80,
            )
            placeholder.add_css_class('search-poster')
            poster_overlay.set_child(placeholder)
        box.append(poster_overlay)

        # Metadata column
        meta = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3,
                        hexpand=True, valign=Gtk.Align.CENTER)

        # Title
        meta.append(Gtk.Label(
            label=entry.get('main', ''), xalign=0,
            ellipsize=3, lines=2, wrap=True,
            css_classes=['heading'],
        ))

        # Subtitle
        parts = []
        if entry.get('type'):
            parts.append(entry['type'])
        if entry.get('year'):
            parts.append(str(entry['year']))
        ep_total = entry.get('episodes_total')
        if ep_total:
            parts.append(f'{ep_total} ' + _('ep.'))
        if entry.get('is_ongoing'):
            parts.append(_('ongoing'))
        if parts:
            meta.append(Gtk.Label(
                label=' · '.join(parts), xalign=0,
                css_classes=['dim-label', 'caption'],
            ))

        # Genre chips
        genre_ids = entry.get('genres', [])
        if genre_ids:
            cached_genres = search_index.get_genres()
            if cached_genres:
                genre_map = {g['id']: g['name'] for g in cached_genres}
                chips_box = Gtk.Box(spacing=4, margin_top=2)
                for gid in genre_ids[:3]:
                    name = genre_map.get(gid)
                    if name:
                        chips_box.append(Gtk.Label(
                            label=name,
                            css_classes=['caption', 'dim-label'],
                            margin_start=6, margin_end=6,
                            margin_top=2, margin_bottom=2,
                        ))
                if chips_box.get_first_child():
                    meta.append(chips_box)

        # Tag badges
        release_id = entry.get('id')
        if release_id:
            tags = tags_store.get_tags_for_release(release_id)
            if tags:
                tags_box = Gtk.Box(spacing=4)
                for tag in tags[:4]:
                    if tag['icon_type'] == 'emoji':
                        tags_box.append(Gtk.Label(label=tag['icon_value']))
                    else:
                        from kitsune.ui.widgets.tag_card import create_color_circle
                        tags_box.append(create_color_circle(
                            tag['icon_value'], 16))
                if len(tags) > 4:
                    tags_box.append(Gtk.Label(
                        label=f'+{len(tags) - 4}',
                        css_classes=['dim-label', 'caption'],
                    ))
                meta.append(tags_box)

        # Watch progress
        if release_id:
            self._add_watch_progress(meta, release_id, ep_total, entry)

        box.append(meta)

        row = Gtk.ListBoxRow(child=box)
        row._search_type = 'anime'
        row._search_data = entry
        return row

    def _add_watch_progress(self, meta, release_id, ep_total, entry):
        positions = watch_positions.get_all_for_release(release_id)
        if not positions:
            return

        completed = sum(1 for p in positions.values() if p == -1)
        watching_ordinal = None
        watching_position = 0
        for ordinal, pos in sorted(positions.items(), reverse=True):
            if pos > 0:
                watching_ordinal = ordinal
                watching_position = pos
                break

        # Episodes progress bar
        if ep_total and ep_total > 0:
            all_done = completed >= ep_total
            fraction = min(completed / ep_total, 1.0)

            bar = Gtk.ProgressBar(fraction=fraction, hexpand=True)
            bar.set_size_request(-1, 3)
            bar.add_css_class('osd')

            progress_box = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
            progress_box.append(bar)

            if all_done:
                progress_box.append(Gtk.Label(
                    label=f'{ep_total} / {ep_total} ✓',
                    css_classes=['caption'],
                ))
            else:
                progress_box.append(Gtk.Label(
                    label=f'{completed} / {ep_total}',
                    css_classes=['caption', 'dim-label'],
                ))
            meta.append(progress_box)

        # New episode takes priority over continue block
        max_completed = max(
            (o for o, p in positions.items() if p == -1), default=0
        )
        new_ep = self._find_new_episode(release_id, max_completed)
        if new_ep:
            self._add_new_episode_block(meta, release_id, new_ep, entry)
        elif watching_ordinal is not None:
            episode_data = self._get_episode_data(release_id, watching_ordinal)
            self._add_continue_block(meta, release_id, watching_ordinal,
                                     watching_position, episode_data, entry)

    def _get_episode_data(self, release_id, ordinal):
        raw = release_cache.get(release_id)
        if not raw:
            return None
        for ep in raw.get('episodes', []):
            if ep.get('ordinal') == ordinal:
                return ep
        return None

    def _find_new_episode(self, release_id, max_completed_ordinal):
        raw = release_cache.get(release_id)
        if not raw:
            return None
        episodes = sorted(raw.get('episodes', []),
                          key=lambda e: e.get('sort_order', 0))
        positions = watch_positions.get_all_for_release(release_id)
        for ep in episodes:
            ordinal = ep.get('ordinal', 0)
            if ordinal > max_completed_ordinal and ordinal not in positions:
                return ep
        return None

    def _add_continue_block(self, meta, release_id, ordinal,
                             position, ep_data, entry):
        duration = ep_data.get('duration') if ep_data else None
        preview_url = None
        if ep_data and ep_data.get('preview'):
            from kitsune.models.release import _poster_preview_url
            preview_url = _poster_preview_url(ep_data.get('preview'))

        btn = Gtk.Button(css_classes=['flat'])
        btn_box = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)

        if preview_url:
            thumb = Gtk.Picture(
                width_request=64, height_request=36,
                content_fit=Gtk.ContentFit.COVER,
            )
            thumb.add_css_class('card')
            from kitsune.ui.image_cache import load_image
            load_image(preview_url, lambda tex, err, p=thumb:
                       p.set_paintable(tex) if tex else None,
                       category='previews')
            btn_box.append(thumb)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        ordinal_str = int(ordinal) if ordinal == int(ordinal) else ordinal
        info.append(Gtk.Label(
            label=_('Episode') + f' {ordinal_str}',
            xalign=0, css_classes=['caption'],
        ))
        if duration and duration > 0:
            pos_str = f'{int(position) // 60}:{int(position) % 60:02d}'
            dur_str = f'{duration // 60}:{duration % 60:02d}'
            info.append(Gtk.Label(
                label=f'{pos_str} / {dur_str}',
                xalign=0, css_classes=['caption', 'dim-label'],
            ))
        btn_box.append(info)

        btn.set_child(btn_box)
        btn.connect('clicked', self._on_episode_clicked,
                     release_id, ordinal, entry)
        meta.append(btn)

    def _add_new_episode_block(self, meta, release_id, ep_data, entry):
        ordinal = ep_data.get('ordinal', 0)
        btn = Gtk.Button(css_classes=['flat'])
        btn_box = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        ordinal_str = int(ordinal) if ordinal == int(ordinal) else ordinal
        info.append(Gtk.Label(
            label=_('New episode') + f' {ordinal_str}',
            xalign=0, css_classes=['caption', 'accent'],
        ))
        btn_box.append(info)

        btn.set_child(btn_box)
        btn.connect('clicked', self._on_episode_clicked,
                     release_id, ordinal, entry)
        meta.append(btn)

    # --- Genre / Franchise / Tag rows ---

    def _make_genre_row(self, item):
        box = Gtk.Box(spacing=10)
        box.add_css_class('search-result-row')
        img_url = item.get('image')
        if img_url:
            pic = Gtk.Picture(width_request=36, height_request=36,
                              content_fit=Gtk.ContentFit.COVER)
            pic.set_size_request(36, 36)
            pic.add_css_class('search-poster')
            from kitsune.ui.image_cache import load_image
            load_image(img_url, lambda tex, err, p=pic:
                       p.set_paintable(tex) if tex else None,
                       category='posters')
            box.append(pic)
        else:
            box.append(Gtk.Image(
                icon_name='tag-symbolic', pixel_size=20,
                width_request=36, height_request=36,
                opacity=0.4,
            ))
        label_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                             hexpand=True, valign=Gtk.Align.CENTER)
        label_box.append(Gtk.Label(label=item.get('name', ''), xalign=0))
        box.append(label_box)
        count = item.get('total_releases', 0)
        if count:
            box.append(Gtk.Label(
                label=str(count), css_classes=['dim-label', 'caption'],
                valign=Gtk.Align.CENTER,
            ))
        row = Gtk.ListBoxRow(child=box)
        row._search_type = 'genre'
        row._search_data = item
        return row

    def _make_franchise_row(self, item):
        box = Gtk.Box(spacing=10)
        box.add_css_class('search-result-row')
        img_url = item.get('image')
        if img_url:
            pic = Gtk.Picture(width_request=36, height_request=36,
                              content_fit=Gtk.ContentFit.COVER)
            pic.set_size_request(36, 36)
            pic.add_css_class('search-poster')
            from kitsune.ui.image_cache import load_image
            load_image(img_url, lambda tex, err, p=pic:
                       p.set_paintable(tex) if tex else None,
                       category='posters')
            box.append(pic)
        else:
            box.append(Gtk.Image(
                icon_name='folder-symbolic', pixel_size=20,
                width_request=36, height_request=36,
                opacity=0.4,
            ))
        label_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                             hexpand=True, valign=Gtk.Align.CENTER)
        label_box.append(Gtk.Label(label=item.get('name', ''), xalign=0))
        parts = []
        fy = item.get('first_year')
        ly = item.get('last_year')
        if fy and ly:
            parts.append(f'{fy}–{ly}')
        tr = item.get('total_releases')
        if tr:
            parts.append(f'{tr} ' + _('titles'))
        if parts:
            label_box.append(Gtk.Label(
                label=' · '.join(parts), xalign=0,
                css_classes=['dim-label', 'caption'],
            ))
        box.append(label_box)
        row = Gtk.ListBoxRow(child=box)
        row._search_type = 'franchise'
        row._search_data = item
        return row

    def _make_tag_row(self, item):
        box = Gtk.Box(spacing=10)
        box.add_css_class('search-result-row')
        if item.get('icon_type') == 'emoji':
            box.append(Gtk.Label(label=item.get('icon_value', ''),
                                  width_request=28))
        else:
            from kitsune.ui.widgets.tag_card import create_color_circle
            box.append(create_color_circle(item.get('icon_value', 'blue'), 28))
        label_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        label_box.append(Gtk.Label(label=item.get('name', ''), xalign=0))
        box.append(label_box)
        count = len(item.get('releases', []))
        if count:
            box.append(Gtk.Label(
                label=str(count), css_classes=['dim-label', 'caption'],
            ))
        row = Gtk.ListBoxRow(child=box)
        row._search_type = 'tag'
        row._search_data = item
        return row

    # --- Activation ---

    @Gtk.Template.Callback()
    def on_row_activated(self, _listbox, row):
        if not hasattr(row, '_search_type'):
            return
        self.close()
        stype = row._search_type
        data = row._search_data
        if stype == 'anime':
            self._activate_anime(data)
        elif stype == 'genre':
            self._activate_genre(data)
        elif stype == 'franchise':
            self._activate_franchise(data)
        elif stype == 'tag':
            self._activate_tag(data)

    def _activate_anime(self, entry):
        release = Release(
            id=entry['id'],
            name=ReleaseName(
                main=entry.get('main', ''),
                english=entry.get('english'),
                alternative=entry.get('alternative'),
            ),
            alias='',
            type=entry.get('type', ''),
            year=entry.get('year', 0),
            is_ongoing=entry.get('is_ongoing', False),
        )
        if self._on_release_activated:
            self._on_release_activated(release)

    def _activate_genre(self, item):
        genre = Genre(
            id=item['id'], name=item['name'],
            image=item.get('image'),
            total_releases=item.get('total_releases', 0),
        )
        if self._on_genre_activated:
            self._on_genre_activated(genre)

    def _activate_franchise(self, item):
        franchise = Franchise(
            id=item['id'], name=item['name'],
            name_english=item.get('name_english'),
            image=item.get('image'),
            first_year=item.get('first_year'),
            last_year=item.get('last_year'),
            total_releases=item.get('total_releases'),
        )
        if self._on_franchise_activated:
            self._on_franchise_activated(franchise)

    def _activate_tag(self, item):
        if self._on_tag_activated:
            self._on_tag_activated(item)

    def _on_episode_clicked(self, _btn, release_id, ordinal, entry):
        self.close()
        if not self._on_episode_play:
            return
        raw = release_cache.get(release_id)
        if not raw:
            self._activate_anime(entry)
            return
        release = Release.from_dict(raw)
        for ep in release.episodes:
            if ep.ordinal == ordinal:
                self._on_episode_play(release, ep)
                return
        self._activate_anime(entry)

    # --- Keyboard ---

    def _setup_keyboard(self):
        ctrl = Gtk.EventControllerKey()
        ctrl.connect('key-pressed', self._on_key_pressed)
        self.add_controller(ctrl)

    def _on_key_pressed(self, ctrl, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True

        focus = self.get_focus()
        in_entry = isinstance(focus, Gtk.SearchEntry) or focus == self.search_entry

        if not in_entry:
            if keyval == Gdk.KEY_Left:
                self._switch_tab(-1)
                return True
            elif keyval == Gdk.KEY_Right:
                self._switch_tab(1)
                return True

            if keyval == Gdk.KEY_BackSpace:
                text = self.search_entry.get_text()
                if text:
                    self.search_entry.set_text(text[:-1])
                    self.search_entry.set_position(-1)
                self.search_entry.grab_focus()
                return True

            if keyval >= 32 and not (state & (Gdk.ModifierType.CONTROL_MASK |
                                               Gdk.ModifierType.ALT_MASK)):
                self.search_entry.grab_focus()
                return False

        return False

    def _switch_tab(self, direction):
        visible = [cid for cid, btn in self._tab_buttons.items()
                   if btn.get_visible()]
        if not visible:
            return
        current = None
        for cid, btn in self._tab_buttons.items():
            if btn.get_active():
                current = cid
                break
        if current is None:
            target = visible[0]
        else:
            try:
                i = visible.index(current)
                i = (i + direction) % len(visible)
                target = visible[i]
            except ValueError:
                target = visible[0]
        self._tab_buttons[target].set_active(True)

    # --- Cleanup ---

    def _on_closed(self, _dialog):
        if self._debounce_id:
            GLib.source_remove(self._debounce_id)
            self._debounce_id = 0
        if self._cancellable:
            self._cancellable.cancel()
            self._cancellable = None
