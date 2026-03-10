# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from kitsune.api import AniLibriaClient

log = logging.getLogger('kitsune.ui.release')
from kitsune.models import Release, Episode
from kitsune.ui.image_cache import load_image
from kitsune import release_cache, watch_positions

_css_loaded = False


def _ensure_css():
    global _css_loaded
    if _css_loaded:
        return
    _css_loaded = True
    css = Gtk.CssProvider()
    css.load_from_string(
        '.release-chip { padding: 4px 10px; border-radius: 9999px;'
        ' background: alpha(currentColor, 0.1);'
        ' transition: background 150ms ease-in-out; }'
        ' .release-chip:hover { background: alpha(currentColor, 0.18); }'
        ' .poster-fade { background: linear-gradient(to bottom,'
        ' transparent 40%, @window_bg_color 100%); }'
        ' .episode-card { border-radius: 12px;'
        ' background: alpha(currentColor, 0.08); }'
        ' .episode-overlay { background: linear-gradient(to top,'
        ' alpha(black, 0.7) 0%, transparent 50%); }'
        ' .ep-overlay-text { color: white; text-shadow: 0 1px 3px alpha(black, 0.8); }'
        ' .episode-progress { min-height: 4px; border-radius: 0; }'
        ' .episode-progress trough { min-height: 4px; background: alpha(white, 0.3); }'
        ' .episode-progress progress { min-height: 4px; background: @accent_bg_color; }'
        ' .episode-blur { filter: blur(8px); }'
        ' .episode-check { background: alpha(black, 0.6); border-radius: 50%;'
        '   min-width: 24px; min-height: 24px; padding: 2px;'
        '   color: @accent_color; text-shadow: none; }'
        ' .episode-separator { min-height: 1px;'
        '   background-color: rgba(200, 200, 200, 0.6); padding: 0; margin: 0; }'
        ' .list-progress { margin-top: 4px; }'
        ' .list-progress trough { min-height: 4px; }'
        ' .list-progress progress { min-height: 4px; background: @accent_bg_color; }'
    )
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), css,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


def _format_size(size_bytes: int) -> str:
    if size_bytes >= 1_073_741_824:
        return f'{size_bytes / 1_073_741_824:.2f} GB'
    if size_bytes >= 1_048_576:
        return f'{size_bytes / 1_048_576:.1f} MB'
    return f'{size_bytes / 1024:.0f} KB'


@Gtk.Template(resource_path='/net/armatik/Kitsune/release_view.ui')
class ReleaseView(Adw.NavigationPage):
    __gtype_name__ = 'KitsuneReleaseView'

    toolbar = Gtk.Template.Child()
    header_bar = Gtk.Template.Child()
    scrolled = Gtk.Template.Child()
    hero = Gtk.Template.Child()
    header = Gtk.Template.Child()
    poster = Gtk.Template.Child()
    info_box = Gtk.Template.Child()
    bg_wrapper = Gtk.Template.Child()
    bg_poster = Gtk.Template.Child()
    content_area = Gtk.Template.Child()
    description_label = Gtk.Template.Child()
    gradient_bg = Gtk.Template.Child()

    tabs_header = Gtk.Template.Child()
    tabs_carousel = Gtk.Template.Child()

    episodes_page = Gtk.Template.Child()
    episodes_toolbar = Gtk.Template.Child()
    episodes_search = Gtk.Template.Child()
    episodes_controls = Gtk.Template.Child()
    episodes_spinner = Gtk.Template.Child()
    episodes_list = Gtk.Template.Child()
    episodes_grid = Gtk.Template.Child()

    related_page = Gtk.Template.Child()
    related_spinner = Gtk.Template.Child()
    related_empty = Gtk.Template.Child()
    related_header = Gtk.Template.Child()
    related_list = Gtk.Template.Child()

    team_page = Gtk.Template.Child()
    team_empty = Gtk.Template.Child()
    team_list = Gtk.Template.Child()

    torrents_page = Gtk.Template.Child()
    torrents_empty = Gtk.Template.Child()
    torrents_list = Gtk.Template.Child()

    _TAB_PAGES = ('episodes', 'related', 'team', 'torrents')

    def __init__(self, release: Release, client: AniLibriaClient, **kwargs):
        super().__init__(title=release.name.main, **kwargs)
        self._release = release
        self._client = client
        self._on_episode_play = None
        self._narrow_mode = False
        self._fade_anim = None
        self._accent_mode = False
        self._franchise = None
        self._episodes_view = 'list'  # overridden from settings below
        self._sort_newest_first = False
        self._search_text = ''
        self._refresh_fade_anim = None
        self._refresh_timer = 0
        self._watch_data = {}
        self._watch_filter = 'all'
        _ensure_css()

        self._settings = Gio.Settings(schema_id='net.armatik.Kitsune')

        self._vadjustment = self.scrolled.get_vadjustment()
        self._vadjustment.connect('value-changed', self._on_scroll)

        # Try loading cached release data
        cached = release_cache.get(release.id)
        if cached:
            self._release = Release.from_dict(cached)

        self._setup_tabs_toggle()
        self._setup_episodes_controls()
        self._populate_info()

        if self._release.poster:
            self._load_poster(self._release.poster)

        if self._release.episodes:
            self._populate_episodes()
            self._apply_episodes_view()
        else:
            self.episodes_spinner.set_visible(True)

        self._populate_team()
        self._populate_torrents()
        self._load_related()

        # Header refresh indicator
        self._header_spinner = Adw.Spinner()
        self._header_check = Gtk.Image(
            icon_name='object-select-symbolic',
            css_classes=['success'],
        )
        self._header_check.set_opacity(0)
        self._header_status = Gtk.Box()
        self._header_status.append(self._header_spinner)
        self.header_bar.pack_end(self._header_status)

        # Always refresh from API
        self._start_refresh()

        self.connect('realize', self._on_realize)
        self.connect('showing', self._on_showing)

    def set_on_episode_play(self, callback):
        self._on_episode_play = callback

    def set_on_genre_clicked(self, callback):
        self._on_genre_navigate = callback

    def _on_showing(self, _page):
        """Refresh episode progress when returning from player."""
        self._refresh_episodes()
        if self._episodes_view == 'grid':
            self._refresh_episodes_grid()

    # --- Tabs (ToggleGroup + Carousel) ---

    _TAB_LABELS = {
        'episodes': _('Episodes'),
        'related': _('Related'),
        'team': _('Team'),
        'torrents': _('Torrents'),
    }

    def _setup_tabs_toggle(self):
        self._tabs_toggle = Adw.ToggleGroup()
        self._visible_tabs = []

        # Store page widget references before removing
        self._tab_pages = {}
        for i, name in enumerate(self._TAB_PAGES):
            self._tab_pages[name] = self.tabs_carousel.get_nth_page(i)

        has_data = {
            'episodes': True,
            'related': False,  # async, added later
            'team': bool(self._release.members),
            'torrents': bool(self._release.torrents),
        }

        # Remove pages without data from carousel (in reverse to keep indices stable)
        for name in reversed(self._TAB_PAGES):
            if not has_data.get(name):
                log.debug('tab %s hidden: no data', name)
                self.tabs_carousel.remove(self._tab_pages[name])

        for name in self._TAB_PAGES:
            if has_data.get(name):
                self._visible_tabs.append(name)
                self._tabs_toggle.add(
                    Adw.Toggle(name=name, label=self._TAB_LABELS[name])
                )

        log.debug('visible tabs: %s', self._visible_tabs)

        self._tabs_toggle.set_active_name('episodes')
        self._tabs_toggle.connect('notify::active-name', self._on_tab_changed)
        self.tabs_header.append(self._tabs_toggle)

    def _add_tab(self, name):
        if name in self._visible_tabs:
            return
        log.debug('adding tab %s (async data arrived)', name)

        # Find correct insertion position in carousel
        insert_before = None
        found = False
        for tab_name in self._TAB_PAGES:
            if tab_name == name:
                found = True
                continue
            if found and tab_name in self._visible_tabs:
                insert_before = tab_name
                break

        if insert_before:
            self.tabs_carousel.insert(
                self._tab_pages[name],
                self._visible_tabs.index(insert_before),
            )
        else:
            self.tabs_carousel.append(self._tab_pages[name])

        # Insert into visible_tabs at correct position
        idx = list(self._TAB_PAGES).index(name)
        insert_at = 0
        for i, t in enumerate(self._visible_tabs):
            if list(self._TAB_PAGES).index(t) < idx:
                insert_at = i + 1
        self._visible_tabs.insert(insert_at, name)

        self._tabs_toggle.add(
            Adw.Toggle(name=name, label=self._TAB_LABELS[name])
        )

    def _on_tab_changed(self, toggle_group, _pspec):
        name = toggle_group.get_active_name()
        if name not in self._visible_tabs:
            return
        idx = self._visible_tabs.index(name)
        page = self.tabs_carousel.get_nth_page(idx)
        self.tabs_carousel.scroll_to(page, True)

    # --- Episodes controls ---

    def _setup_episodes_controls(self):
        # Search
        self.episodes_search.connect('search-changed', self._on_episodes_search_changed)
        self.episodes_controls.set_spacing(6)

        # Filter: All / Watched / Unwatched (wide mode)
        self._filter_toggle = Adw.ToggleGroup()
        self._filter_toggle.add(Adw.Toggle(name='all', label=_('All')))
        self._filter_toggle.add(Adw.Toggle(name='watched', label=_('Watched')))
        self._filter_toggle.add(Adw.Toggle(name='unwatched', label=_('Unwatched')))
        self._filter_toggle.set_active_name('all')
        self._filter_toggle.connect('notify::active-name', self._on_filter_changed)
        self.episodes_controls.append(self._filter_toggle)

        # Filter: MenuButton (compact mode, hidden by default)
        self._filter_menu_btn = Gtk.MenuButton(
            icon_name='funnel-symbolic',
            visible=False,
        )
        popover = Gtk.Popover()
        self._filter_pop_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self._filter_pop_list.add_css_class('boxed-list')
        self._filter_rows = []
        for name, label in [('all', _('All')), ('watched', _('Watched')), ('unwatched', _('Unwatched'))]:
            row = Adw.ActionRow(title=label, activatable=True)
            row._filter_name = name
            self._filter_rows.append(row)
            self._filter_pop_list.append(row)
        self._filter_rows[0].add_prefix(Gtk.Image(icon_name='object-select-symbolic'))
        self._filter_pop_list.connect('row-activated', self._on_filter_row_activated)
        popover.set_child(self._filter_pop_list)
        self._filter_menu_btn.set_popover(popover)
        self.episodes_controls.append(self._filter_menu_btn)

        # Sort toggle
        sort_box = Gtk.Box(css_classes=['linked'])
        self._sort_btn = Gtk.Button(
            icon_name='view-sort-descending-symbolic',
            tooltip_text=_('Newest first'),
        )
        self._sort_btn.connect('clicked', self._on_sort_clicked)
        sort_box.append(self._sort_btn)
        self.episodes_controls.append(sort_box)

        # View toggle (list / grid)
        saved_view = self._settings.get_string('episodes-view')
        self._episodes_view = saved_view if saved_view in ('list', 'grid') else 'list'

        self._view_toggle = Adw.ToggleGroup()
        self._view_toggle.add(Adw.Toggle(
            name='list', icon_name='view-list-symbolic',
            tooltip=_('List view'),
        ))
        self._view_toggle.add(Adw.Toggle(
            name='grid', icon_name='view-grid-symbolic',
            tooltip=_('Grid view'),
        ))
        self._view_toggle.set_active_name(self._episodes_view)
        self._view_toggle.connect('notify::active-name', self._on_episodes_view_changed)
        self.episodes_controls.append(self._view_toggle)

        # Mark all watched / Unmark all
        mark_box = Gtk.Box(css_classes=['linked'])
        mark_btn = Gtk.Button(
            icon_name='object-select-symbolic',
            tooltip_text=_('Mark all as watched'),
            sensitive=False,
        )
        unmark_btn = Gtk.Button(
            icon_name='cross-large-symbolic',
            tooltip_text=_('Unmark all'),
            sensitive=False,
        )
        mark_box.append(mark_btn)
        mark_box.append(unmark_btn)
        self.episodes_controls.append(mark_box)

    def _on_episodes_view_changed(self, toggle, _pspec):
        name = toggle.get_active_name()
        self._episodes_view = name
        self._settings.set_string('episodes-view', name)
        if name == 'grid':
            self.episodes_list.set_visible(False)
            self.episodes_grid.set_visible(True)
            self._refresh_episodes_grid()
        else:
            self.episodes_list.set_visible(True)
            self.episodes_grid.set_visible(False)

    def _apply_episodes_view(self):
        if self._episodes_view == 'grid':
            self.episodes_list.set_visible(False)
            self.episodes_grid.set_visible(True)
            self._populate_episodes_grid()
        else:
            self.episodes_list.set_visible(True)
            self.episodes_grid.set_visible(False)

    def _on_episodes_search_changed(self, entry):
        self._search_text = entry.get_text().strip().lower()
        self._refresh_episodes()

    def _on_filter_changed(self, toggle_group, _pspec):
        self._watch_filter = toggle_group.get_active_name()
        self._refresh_episodes()

    def _on_filter_row_activated(self, listbox, row):
        name = row._filter_name
        self._watch_filter = name
        self._filter_toggle.set_active_name(name)
        for r in self._filter_rows:
            child = r.get_first_child()
            while child:
                if isinstance(child, Gtk.Image):
                    r.remove(child)
                    break
                child = child.get_next_sibling()
        row.add_prefix(Gtk.Image(icon_name='object-select-symbolic'))
        self._filter_menu_btn.get_popover().popdown()
        self._refresh_episodes()

    def _on_sort_clicked(self, _button):
        self._sort_newest_first = not self._sort_newest_first
        if self._sort_newest_first:
            self._sort_btn.set_icon_name('view-sort-ascending-symbolic')
            self._sort_btn.set_tooltip_text(_('Oldest first'))
        else:
            self._sort_btn.set_icon_name('view-sort-descending-symbolic')
            self._sort_btn.set_tooltip_text(_('Newest first'))
        self._refresh_episodes()

    def _get_filtered_episodes(self) -> list[Episode]:
        episodes = list(self._release.episodes)
        if self._watch_filter == 'watched':
            episodes = [ep for ep in episodes
                        if self._watch_data.get(ep.ordinal, 0) != 0]
        elif self._watch_filter == 'unwatched':
            episodes = [ep for ep in episodes
                        if self._watch_data.get(ep.ordinal, 0) == 0]
        if self._search_text:
            query = self._search_text
            filtered = []
            for ep in episodes:
                ordinal = int(ep.ordinal) if ep.ordinal == int(ep.ordinal) else ep.ordinal
                if query in str(ordinal):
                    filtered.append(ep)
                elif ep.name and query in ep.name.lower():
                    filtered.append(ep)
            episodes = filtered
        if self._sort_newest_first:
            episodes = list(reversed(episodes))
        return episodes

    def _refresh_episodes(self):
        self._populate_episodes()
        if self._episodes_view == 'grid':
            self._refresh_episodes_grid()

    def _refresh_episodes_grid(self):
        if self.episodes_grid.get_visible():
            self._populate_episodes_grid()

    # --- Info ---

    def _populate_info(self):
        title_label = Gtk.Label(
            label=self._release.name.main,
            wrap=True, xalign=0, css_classes=['title-1'],
            use_markup=False,
        )
        self.info_box.append(title_label)

        if self._release.name.english:
            en_label = Gtk.Label(
                label=self._release.name.english,
                wrap=True, xalign=0, css_classes=['dim-label'],
                use_markup=False,
            )
            self.info_box.append(en_label)

        if self._release.genres:
            genre_wrap = Adw.WrapBox(
                line_spacing=6, child_spacing=6, margin_top=8,
            )
            for genre in self._release.genres:
                btn = Gtk.Button(
                    label=genre.name,
                    css_classes=['pill', 'release-chip'],
                )
                btn.connect('clicked', lambda _b, g=genre: self._on_genre_clicked(g))
                genre_wrap.append(btn)
            self.info_box.append(genre_wrap)

        meta_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_top=12,
        )
        if self._release.type:
            meta_box.append(self._meta_row(_('Type'), self._release.type))
        if self._release.year:
            meta_box.append(self._meta_row(_('Year'), str(self._release.year)))
        if self._release.season:
            meta_box.append(self._meta_row(_('Season'), self._release.season))
        if self._release.age_rating:
            meta_box.append(self._meta_row(
                _('Age rating'), self._format_age_rating(self._release.age_rating),
            ))
        if self._release.episodes_total:
            meta_box.append(self._meta_row(
                _('Episodes'), str(self._release.episodes_total),
            ))
        status = _('Ongoing') if self._release.is_ongoing else _('Completed')
        meta_box.append(self._meta_row(_('Status'), status))
        self.info_box.append(meta_box)

        if self._release.description:
            self.description_label.set_label(self._release.description)
            self.description_label.set_visible(True)

    # --- Episodes (list) ---

    def _start_refresh(self):
        self._client.get_release_raw(
            self._release.alias or str(self._release.id),
            callback=self._on_raw_release_loaded,
        )

    def _on_raw_release_loaded(self, data, error):
        self.episodes_spinner.set_visible(False)
        if error or not data:
            self._show_refresh_error()
            if not self._release.episodes:
                self._show_spinner_error(self.episodes_spinner)
            return

        release_cache.save(self._release.id, data)
        self._release = Release.from_dict(data)

        # Clear and repopulate info
        while child := self.info_box.get_first_child():
            self.info_box.remove(child)
        self._populate_info()

        self._populate_episodes()
        self._apply_episodes_view()
        self._populate_team()
        self._populate_torrents()
        if self._release.members:
            self._add_tab('team')
        if self._release.torrents:
            self._add_tab('torrents')
        self.tabs_carousel.queue_resize()

        self._show_refresh_done()

    def _show_refresh_error(self):
        self._header_spinner.set_visible(False)
        error = Gtk.Image(
            icon_name='cross-large-symbolic',
            css_classes=['error'],
        )
        self._header_status.append(error)

    def _show_spinner_error(self, spinner):
        spinner.set_visible(False)
        error = Gtk.Image(
            icon_name='cross-large-symbolic',
            pixel_size=32,
            css_classes=['error'],
            halign=Gtk.Align.CENTER,
        )
        parent = spinner.get_parent()
        parent.insert_child_after(error, spinner)

    def _show_refresh_done(self):
        self._header_spinner.set_visible(False)
        self._header_check.set_opacity(1)
        self._header_status.append(self._header_check)
        self._refresh_timer = GLib.timeout_add(3000, self._fade_checkmark)

    def _fade_checkmark(self):
        self._refresh_timer = 0
        target = Adw.PropertyAnimationTarget.new(self._header_check, 'opacity')
        self._refresh_fade_anim = Adw.TimedAnimation.new(
            self._header_check, 1.0, 0.0, 500, target,
        )
        self._refresh_fade_anim.play()
        return GLib.SOURCE_REMOVE

    def _load_watch_data(self):
        self._watch_data = watch_positions.get_all_for_release(self._release.id)

    def _populate_episodes(self):
        while child := self.episodes_list.get_first_child():
            self.episodes_list.remove(child)

        self._load_watch_data()

        for episode in self._get_filtered_episodes():
            pos = self._watch_data.get(episode.ordinal, 0)

            row = Adw.ActionRow(
                title=self._episode_title(episode),
                subtitle=self._episode_subtitle(episode),
                activatable=True,
                use_markup=False,
            )
            if pos == -1:
                check = Gtk.Image(
                    icon_name='object-select-symbolic',
                    css_classes=['accent'],
                    valign=Gtk.Align.CENTER,
                )
                row.add_suffix(check)
            elif pos > 0 and episode.duration and episode.duration > 0:
                fraction = min(1.0, max(0.0, pos / episode.duration))
                prog = Gtk.ProgressBar(
                    fraction=fraction,
                    valign=Gtk.Align.CENTER,
                    css_classes=['list-progress'],
                )
                prog.set_size_request(60, -1)
                row.add_suffix(prog)

            play_btn = Gtk.Button(
                icon_name='media-playback-start-symbolic',
                valign=Gtk.Align.CENTER, css_classes=['flat'],
            )
            play_btn.connect('clicked', self._on_play_clicked, episode)
            row.add_suffix(play_btn)

            row.connect('activated', lambda _r, ep=episode: self._play_episode(ep))
            self.episodes_list.append(row)

    # --- Episodes (grid) ---

    def _populate_episodes_grid(self):
        while child := self.episodes_grid.get_first_child():
            self.episodes_grid.remove(child)

        self._load_watch_data()

        for episode in self._get_filtered_episodes():
            card = self._build_episode_card(episode)
            self.episodes_grid.append(card)

    _EP_CARD_W = 240
    _EP_CARD_H = 135  # 16:9

    def _build_episode_card(self, episode: Episode) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        pos = self._watch_data.get(episode.ordinal, 0)

        clamp = Adw.Clamp(maximum_size=self._EP_CARD_W)

        overlay = Gtk.Overlay(
            css_classes=['episode-card'],
            width_request=self._EP_CARD_W,
            height_request=self._EP_CARD_H,
        )
        overlay.set_overflow(Gtk.Overflow.HIDDEN)
        overlay.set_cursor(Gdk.Cursor.new_from_name('pointer'))

        pic_classes = []
        if pos == 0 and self._settings.get_boolean('blur-unwatched-episodes'):
            pic_classes.append('episode-blur')

        picture = Gtk.Picture(
            content_fit=Gtk.ContentFit.COVER,
            width_request=self._EP_CARD_W,
            height_request=self._EP_CARD_H,
            css_classes=pic_classes,
        )
        overlay.set_child(picture)

        if episode.preview:
            spinner = Adw.Spinner(
                halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
                width_request=32, height_request=32,
            )
            overlay.add_overlay(spinner)

            def _on_preview_loaded(tex, err, pic=picture, sp=spinner, ov=overlay):
                sp.set_visible(False)
                if tex:
                    pic.set_paintable(tex)
                else:
                    ov.add_overlay(Gtk.Image(
                        icon_name='image-missing-symbolic',
                        pixel_size=48, opacity=0.4,
                        halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
                    ))

            load_image(episode.preview, _on_preview_loaded,
                       category='previews')
        else:
            placeholder = Gtk.Image(
                icon_name='image-missing-symbolic',
                pixel_size=48, opacity=0.4,
                halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
            )
            overlay.add_overlay(placeholder)

        gradient = Gtk.Box(
            css_classes=['episode-overlay'],
            hexpand=True, vexpand=True,
        )
        overlay.add_overlay(gradient)

        ordinal = int(episode.ordinal) if episode.ordinal == int(episode.ordinal) else episode.ordinal

        label_box = Gtk.Box(
            spacing=4, margin_start=10, margin_end=10,
            margin_bottom=8, valign=Gtk.Align.END,
        )

        # Episode number (+ optional name as subtitle)
        if episode.name:
            title_col = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                hexpand=True, spacing=1,
            )
            ep_label = Gtk.Label(
                label=_('Episode {}').format(ordinal),
                xalign=0,
                css_classes=['heading', 'ep-overlay-text'],
            )
            name_label = Gtk.Label(
                label=episode.name,
                xalign=0, ellipsize=3,  # PANGO_ELLIPSIZE_END
                css_classes=['caption', 'ep-overlay-text'],
            )
            title_col.append(ep_label)
            title_col.append(name_label)
            label_box.append(title_col)
        else:
            ep_label = Gtk.Label(
                label=_('Episode {}').format(ordinal),
                xalign=0, hexpand=True,
                css_classes=['heading', 'ep-overlay-text'],
            )
            label_box.append(ep_label)

        if pos > 0 and episode.duration:
            remaining = max(0, episode.duration - pos)
            rem_min = int(remaining) // 60
            rem_label = Gtk.Label(
                label=_('Remaining: {} min').format(rem_min),
                valign=Gtk.Align.END,
                css_classes=['caption', 'ep-overlay-text'],
            )
            label_box.append(rem_label)
        elif episode.duration:
            mins = episode.duration // 60
            secs = episode.duration % 60
            dur_label = Gtk.Label(
                label=f'{mins}:{secs:02d}',
                valign=Gtk.Align.END,
                css_classes=['caption', 'ep-overlay-text'],
            )
            label_box.append(dur_label)
        overlay.add_overlay(label_box)

        # Progress bar at bottom with 1px separator
        if pos != 0 and episode.duration and episode.duration > 0:
            fraction = 1.0 if pos == -1 else min(1.0, max(0.0, pos / episode.duration))
            progress_box = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                valign=Gtk.Align.END,
                hexpand=True,
            )
            separator = Gtk.Box(
                css_classes=['episode-separator'],
                hexpand=True,
            )
            progress_box.append(separator)
            progress_bar = Gtk.ProgressBar(
                fraction=fraction,
                css_classes=['episode-progress'],
            )
            progress_box.append(progress_bar)
            overlay.add_overlay(progress_box)

        # Checkmark for completed
        if pos == -1:
            check_box = Gtk.Box(
                halign=Gtk.Align.END, valign=Gtk.Align.START,
                margin_top=6, margin_end=6,
            )
            check_icon = Gtk.Image(
                icon_name='object-select-symbolic',
                pixel_size=16,
                css_classes=['episode-check'],
            )
            check_box.append(check_icon)
            overlay.add_overlay(check_box)

        gesture = Gtk.GestureClick()
        gesture.connect('released',
                        lambda g, n, x, y, ep=episode: self._play_episode(ep))
        overlay.add_controller(gesture)

        clamp.set_child(overlay)
        box.append(clamp)
        return box

    # --- Episodes helpers ---

    def _episode_title(self, episode: Episode) -> str:
        ordinal = int(episode.ordinal) if episode.ordinal == int(episode.ordinal) else episode.ordinal
        if episode.name:
            return f'{ordinal}. {episode.name}'
        return _('Episode {}').format(ordinal)

    def _episode_subtitle(self, episode: Episode) -> str:
        parts = []
        pos = self._watch_data.get(episode.ordinal, 0)
        if pos == -1 and episode.duration:
            mins = episode.duration // 60
            parts.append(_('Watched') + f' ({mins} ' + _('min') + ')')
        elif pos > 0 and episode.duration:
            remaining = max(0, episode.duration - pos)
            rem_min = int(remaining) // 60
            total_min = episode.duration // 60
            parts.append(_('Remaining: {} min of {} min').format(rem_min, total_min))
        elif episode.duration:
            mins = episode.duration // 60
            parts.append(f'{mins} ' + _('min'))
        qualities = []
        if episode.hls_1080:
            qualities.append('1080p')
        if episode.hls_720:
            qualities.append('720p')
        if episode.hls_480:
            qualities.append('480p')
        if qualities:
            parts.append(' / '.join(qualities))
        return ' \u2014 '.join(parts) if parts else ''

    def _on_play_clicked(self, _button, episode):
        self._play_episode(episode)

    def _play_episode(self, episode: Episode):
        if self._on_episode_play:
            self._on_episode_play(self._release, episode)

    # --- Related (franchise) ---

    def _load_related(self):
        self.related_spinner.set_visible(True)
        self._client.get_franchise_for_release(
            self._release.id,
            callback=self._on_franchise_found,
        )

    def _on_franchise_found(self, franchise, error):
        self.related_spinner.set_visible(False)
        if error:
            return
        if not franchise:
            return
        self._franchise = franchise
        self._add_tab('related')
        self._populate_related()
        self.tabs_carousel.queue_resize()

    def _populate_related(self):
        self.related_spinner.set_visible(False)
        f = self._franchise

        # Franchise header
        self.related_header.set_visible(True)
        title = Gtk.Label(
            label=f.name, xalign=0, wrap=True,
            margin_start=16, margin_end=16, margin_top=12,
            css_classes=['title-4'],
        )
        self.related_header.append(title)

        if f.name_english:
            en = Gtk.Label(
                label=f.name_english, xalign=0, wrap=True,
                margin_start=16, margin_end=16,
                css_classes=['dim-label'],
            )
            self.related_header.append(en)

        meta_parts = []
        if f.first_year and f.last_year:
            meta_parts.append(f'{f.first_year} \u2014 {f.last_year}')
        elif f.first_year:
            meta_parts.append(str(f.first_year))
        if f.total_releases:
            meta_parts.append(
                _('%d seasons') % f.total_releases
                if f.total_releases > 1 else _('1 season')
            )
        if f.total_episodes:
            meta_parts.append(_('%d episodes') % f.total_episodes)
        if f.total_duration:
            meta_parts.append(f.total_duration)

        if meta_parts:
            meta = Gtk.Label(
                label=' \u2022 '.join(meta_parts), xalign=0, wrap=True,
                margin_start=16, margin_end=16, margin_bottom=12,
                css_classes=['dim-label', 'caption'],
            )
            self.related_header.append(meta)

        # Franchise releases
        self.related_list.set_visible(True)
        for idx, release in enumerate(f.releases):
            is_current = release.id == self._release.id

            row = Adw.ActionRow(
                title=release.name.main,
                subtitle=self._related_subtitle(release),
                activatable=not is_current,
                use_markup=False,
            )
            row.add_css_class('heading')

            num_classes = ['title-2']
            num_classes.append('accent' if is_current else 'dim-label')
            num_label = Gtk.Label(
                label=f'#{idx + 1}',
                css_classes=num_classes,
                valign=Gtk.Align.CENTER,
            )
            row.add_suffix(num_label)

            clamp = Adw.Clamp(maximum_size=90, valign=Gtk.Align.CENTER)
            pic_overlay = Gtk.Overlay(
                width_request=90, height_request=126,
                css_classes=['card'],
            )
            pic_overlay.set_overflow(Gtk.Overflow.HIDDEN)
            pic = Gtk.Picture(
                width_request=90, height_request=126,
                content_fit=Gtk.ContentFit.COVER,
            )
            pic_overlay.set_child(pic)
            clamp.set_child(pic_overlay)
            if release.poster:
                load_image(release.poster, lambda tex, err, p=pic:
                           p.set_paintable(tex) if tex else None)
            row.add_prefix(clamp)

            if not is_current:
                row.connect('activated', lambda _r, rel=release:
                            self._on_related_activated(rel))

            self.related_list.append(row)

    def _related_subtitle(self, release: Release) -> str:
        parts = []
        if release.year:
            parts.append(str(release.year))
        if release.season:
            parts.append(release.season)
        if release.type:
            parts.append(release.type)
        if release.episodes_total:
            parts.append(_('%d episodes') % release.episodes_total)
        return ' \u2022 '.join(parts)

    def _on_related_activated(self, release: Release):
        nav = self.get_ancestor(Adw.NavigationView)
        if nav:
            view = ReleaseView(release=release, client=self._client)
            view.set_on_episode_play(self._on_episode_play)
            nav.push(view)

    # --- Team ---

    def _populate_team(self):
        while child := self.team_list.get_first_child():
            self.team_list.remove(child)

        if not self._release.members:
            self.team_empty.set_visible(True)
            return
        self.team_empty.set_visible(False)

        for member in self._release.members:
            row = Adw.ActionRow(
                title=member.nickname,
                subtitle=member.role,
                use_markup=False,
            )
            avatar = Adw.Avatar(size=40, text=member.nickname)
            if member.avatar:
                load_image(member.avatar, lambda tex, err, a=avatar:
                           a.set_custom_image(tex) if tex else None)
            row.add_prefix(avatar)
            self.team_list.append(row)

    # --- Torrents ---

    def _populate_torrents(self):
        while child := self.torrents_list.get_first_child():
            self.torrents_list.remove(child)

        if not self._release.torrents:
            self.torrents_empty.set_visible(True)
            return
        self.torrents_empty.set_visible(False)

        for torrent in self._release.torrents:
            title_parts = []
            if torrent.episode_range:
                title_parts.append(_('Episodes: %s') % torrent.episode_range)
            if torrent.codec:
                title_parts.append(torrent.codec)
            title = '  '.join(title_parts) if title_parts else torrent.label

            subtitle_parts = [_format_size(torrent.size)]
            if torrent.quality:
                subtitle_parts.append(torrent.quality)
            if torrent.seeders:
                subtitle_parts.append(f'\u2191{torrent.seeders}')
            if torrent.leechers:
                subtitle_parts.append(f'\u2193{torrent.leechers}')
            if torrent.completed_times:
                subtitle_parts.append(f'\u2713{torrent.completed_times}')
            if torrent.is_hardsub:
                subtitle_parts.append(_('Hardsub'))

            row = Adw.ActionRow(
                title=title,
                subtitle=' \u2022 '.join(subtitle_parts),
                use_markup=False,
            )

            download_btn = Gtk.Button(
                icon_name='folder-download-symbolic',
                valign=Gtk.Align.CENTER,
                css_classes=['flat'],
                tooltip_text=_('Download torrent'),
            )
            download_btn.connect('clicked', self._on_torrent_download, torrent)
            row.add_suffix(download_btn)

            magnet_btn = Gtk.Button(
                icon_name='magnet-symbolic',
                valign=Gtk.Align.CENTER,
                css_classes=['flat'],
                tooltip_text=_('Open magnet link'),
            )
            magnet_btn.connect('clicked', self._on_magnet_clicked, torrent)
            row.add_suffix(magnet_btn)

            self.torrents_list.append(row)

    def _on_torrent_download(self, _button, torrent):
        from kitsune import API_BASE_URL
        url = f'{API_BASE_URL}/anime/torrents/{int(torrent.id)}/file'
        launcher = Gtk.UriLauncher(uri=url)
        launcher.launch(self.get_root(), None, None, None)

    def _on_magnet_clicked(self, _button, torrent):
        if torrent.magnet and torrent.magnet.startswith('magnet:'):
            launcher = Gtk.UriLauncher(uri=torrent.magnet)
            launcher.launch(self.get_root(), None, None, None)

    # --- Toolbar / scroll ---

    @Gtk.Template.Callback()
    def on_bp_apply(self, _bp):
        self._narrow_mode = True
        self._filter_toggle.set_visible(False)
        self._filter_menu_btn.set_visible(True)
        self.episodes_toolbar.reorder_child_after(self.episodes_controls, None)
        self.episodes_controls.set_halign(Gtk.Align.CENTER)
        self._update_toolbar()
        if self._accent_mode:
            mobile_ok = self._settings.get_boolean('accent-mobile-enabled')
            if not mobile_ok:
                self.gradient_bg.set_opacity(0)

    @Gtk.Template.Callback()
    def on_bp_unapply(self, _bp):
        self._narrow_mode = False
        self._filter_toggle.set_visible(True)
        self._filter_menu_btn.set_visible(False)
        self.episodes_toolbar.reorder_child_after(
            self.episodes_controls, self.episodes_search,
        )
        self.episodes_controls.set_halign(Gtk.Align.FILL)
        self._update_toolbar()
        if self._accent_mode:
            self.gradient_bg.set_opacity(0.3)

    def _on_realize(self, _widget):
        root = self.get_root()
        if root and root.get_width() <= 500:
            self._narrow_mode = True
            self.toolbar.set_top_bar_style(Adw.ToolbarStyle.FLAT)
            self.toolbar.set_extend_content_to_top_edge(True)

    def _update_toolbar(self):
        hero_h = self.hero.get_height()
        past_hero = hero_h > 0 and self._vadjustment.get_value() > hero_h

        if not self._narrow_mode:
            self.toolbar.set_top_bar_style(Adw.ToolbarStyle.FLAT)
            self.toolbar.set_extend_content_to_top_edge(False)
            self.header_bar.set_show_title(past_hero)
            return

        if past_hero:
            self.toolbar.set_top_bar_style(Adw.ToolbarStyle.RAISED)
            self.toolbar.set_extend_content_to_top_edge(False)
            self.header_bar.set_show_title(True)
        else:
            self.toolbar.set_top_bar_style(Adw.ToolbarStyle.FLAT)
            self.toolbar.set_extend_content_to_top_edge(True)
            self.header_bar.set_show_title(False)

    def _on_scroll(self, _adjustment):
        self._update_toolbar()

    # --- Misc ---

    def _on_genre_clicked(self, genre):
        if hasattr(self, '_on_genre_navigate') and self._on_genre_navigate:
            self._on_genre_navigate(genre)

    @staticmethod
    def _meta_row(label, value):
        row = Gtk.Box(spacing=8)
        row.append(Gtk.Label(
            label=f'{label}:',
            css_classes=['dim-label'], xalign=0,
        ))
        row.append(Gtk.Label(label=value, xalign=0, wrap=True, hexpand=True))
        return row

    @staticmethod
    def _format_age_rating(rating: str) -> str:
        mapping = {
            'R0_PLUS': '0+', 'R6_PLUS': '6+', 'R12_PLUS': '12+',
            'R16_PLUS': '16+', 'R18_PLUS': '18+',
        }
        return mapping.get(rating, rating)

    # --- Poster / accent ---

    def _load_poster(self, url: str):
        load_image(url, self._on_poster_loaded)

    def _on_poster_loaded(self, texture, error):
        if texture:
            self.poster.set_paintable(texture)
            self.bg_poster.set_paintable(texture)
            w = texture.get_width()
            h = texture.get_height()
            if w > 0:
                self.poster.set_size_request(250, int(250 * h / w))
            self._apply_page_style(texture)

    def _apply_page_style(self, texture: Gdk.Texture):
        style = self._settings.get_string('release-page-style')
        if style != 'accent':
            return

        n_points = self._settings.get_int('accent-color-points')
        glass = self._settings.get_boolean('accent-glass-effect')

        # Convert texture to PNG bytes on the main thread (GDK is not thread-safe)
        png_bytes = texture.save_to_png_bytes()

        import threading
        from kitsune.ui.color_extractor import extract_colors_from_bytes, create_gradient_bytes

        def _generate():
            colors = extract_colors_from_bytes(png_bytes)
            gradient_data = create_gradient_bytes(colors, n_points=n_points, noise=glass)
            GLib.idle_add(self._on_gradient_ready, gradient_data)

        threading.Thread(target=_generate, daemon=True).start()

    def _on_gradient_ready(self, gradient_data):
        if not self.get_mapped():
            return GLib.SOURCE_REMOVE
        # Create GDK texture on the main thread
        gbytes = GLib.Bytes.new(gradient_data)
        gradient = Gdk.Texture.new_from_bytes(gbytes)
        self.gradient_bg.set_paintable(gradient)
        self._accent_mode = True

        mobile_ok = self._settings.get_boolean('accent-mobile-enabled')
        if self._narrow_mode and not mobile_ok:
            return

        self._start_gradient_fade()

    def _start_gradient_fade(self):
        duration = self._settings.get_int('accent-fade-duration')
        target = Adw.PropertyAnimationTarget.new(self.gradient_bg, 'opacity')
        self._fade_anim = Adw.TimedAnimation.new(self.gradient_bg, 0, 0.3, duration, target)
        self._fade_anim.play()
        return GLib.SOURCE_REMOVE

    def do_unmap(self):
        try:
            if self._fade_anim:
                self._fade_anim.skip()
                self._fade_anim = None
            if self._refresh_fade_anim:
                self._refresh_fade_anim.skip()
                self._refresh_fade_anim = None
            if self._refresh_timer:
                GLib.source_remove(self._refresh_timer)
                self._refresh_timer = 0
        finally:
            Adw.NavigationPage.do_unmap(self)
