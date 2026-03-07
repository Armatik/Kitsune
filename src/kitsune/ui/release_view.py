# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gdk, Gtk

from kitsune.api import AniLibriaClient
from kitsune.models import Release, Episode
from kitsune.ui.image_cache import load_image

_css_loaded = False


def _ensure_css():
    global _css_loaded
    if _css_loaded:
        return
    _css_loaded = True
    css = Gtk.CssProvider()
    css.load_from_string(
        '.release-chip { padding: 4px 10px; border-radius: 9999px;'
        ' background: alpha(currentColor, 0.1); }'
        ' .poster-fade { background: linear-gradient(to bottom,'
        ' transparent 40%, @window_bg_color 100%); }'
    )
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), css,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


class ReleaseView(Adw.NavigationPage):

    def __init__(self, release: Release, client: AniLibriaClient, **kwargs):
        super().__init__(title='', **kwargs)
        self._release = release
        self._client = client
        self._on_episode_play = None
        _ensure_css()
        self._build_ui()
        if not release.episodes:
            self._load_full_release()

    def set_on_episode_play(self, callback):
        self._on_episode_play = callback

    def _load_full_release(self):
        self._spinner.set_visible(True)
        self._client.get_release(
            self._release.alias or str(self._release.id),
            callback=self._on_release_loaded,
        )

    def _on_release_loaded(self, release, error):
        self._spinner.set_visible(False)
        if error or not release:
            return
        self._release = release
        self._populate_episodes()

    def _build_ui(self):
        self._toolbar = Adw.ToolbarView()
        self._toolbar.add_top_bar(Adw.HeaderBar())

        scrolled = Gtk.ScrolledWindow(vexpand=True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._vadjustment = scrolled.get_vadjustment()
        self._vadjustment.connect('value-changed', self._on_scroll)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Hero section: overlay for narrow bg poster effect
        self._hero = Gtk.Overlay()
        self._hero.set_overflow(Gtk.Overflow.HIDDEN)
        self._hero.set_margin_start(24)
        self._hero.set_margin_end(24)
        self._hero.set_margin_top(24)

        # Foreground: poster card + info side by side (child = determines size)
        self._header = Gtk.Box(spacing=24)

        self._poster = Gtk.Picture()
        self._poster.set_size_request(250, 350)
        self._poster.set_content_fit(Gtk.ContentFit.COVER)
        self._poster.set_valign(Gtk.Align.START)
        self._poster.add_css_class('card')
        self._header.append(self._poster)

        info_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            valign=Gtk.Align.END,
            hexpand=True,
        )

        title_label = Gtk.Label(
            label=self._release.name.main,
            wrap=True,
            xalign=0,
            css_classes=['title-1'],
        )
        info_box.append(title_label)

        if self._release.name.english:
            en_label = Gtk.Label(
                label=self._release.name.english,
                wrap=True,
                xalign=0,
                css_classes=['dim-label'],
            )
            info_box.append(en_label)

        # Genre chips
        if self._release.genres:
            genre_wrap = Adw.WrapBox(
                line_spacing=6,
                child_spacing=6,
                margin_top=8,
            )
            for genre in self._release.genres:
                btn = Gtk.Button(
                    label=genre.name,
                    css_classes=['pill', 'release-chip'],
                )
                btn.connect('clicked', self._on_genre_clicked)
                genre_wrap.append(btn)
            info_box.append(genre_wrap)

        # Metadata rows
        meta_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=4,
            margin_top=12,
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

        info_box.append(meta_box)

        self._header.append(info_box)

        # Header is the child — it determines the hero size
        self._hero.set_child(self._header)

        # Background overlay: poster + gradient fade (drawn on top but very faint)
        self._bg_wrapper = Gtk.Overlay()
        self._bg_wrapper.set_opacity(0)

        self._bg_poster = Gtk.Picture()
        self._bg_poster.set_content_fit(Gtk.ContentFit.COVER)
        self._bg_wrapper.set_child(self._bg_poster)

        self._fade = Gtk.Box(css_classes=['poster-fade'])
        self._bg_wrapper.add_overlay(self._fade)

        self._hero.add_overlay(self._bg_wrapper)

        outer.append(self._hero)

        if self._release.poster:
            self._load_poster(self._release.poster)

        # Content below hero (with margins)
        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=24,
            margin_start=24,
            margin_end=24,
            margin_top=24,
            margin_bottom=24,
        )

        # Description
        if self._release.description:
            desc = Gtk.Label(
                label=self._release.description,
                wrap=True,
                xalign=0,
                selectable=True,
            )
            content.append(desc)

        # Episodes section
        episodes_label = Gtk.Label(
            label=_('Episodes'),
            xalign=0,
            css_classes=['title-3'],
        )
        content.append(episodes_label)

        # Spinner for loading episodes
        self._spinner = Adw.Spinner()
        self._spinner.set_halign(Gtk.Align.CENTER)
        self._spinner.set_visible(False)
        content.append(self._spinner)

        self._episodes_list = Gtk.ListBox(
            selection_mode=Gtk.SelectionMode.NONE,
            css_classes=['boxed-list'],
        )
        content.append(self._episodes_list)

        self._populate_episodes()

        outer.append(content)
        scrolled.set_child(outer)

        # Responsive layout via BreakpointBin
        bp_bin = Adw.BreakpointBin(
            width_request=300, height_request=400, vexpand=True,
        )
        bp_bin.set_child(scrolled)

        bp = Adw.Breakpoint.new(
            Adw.BreakpointCondition.parse('max-width: 500px'),
        )
        bp.add_setter(self._bg_wrapper, 'opacity', 0.15)
        bp.add_setter(self._poster, 'visible', False)
        bp.add_setter(self._hero, 'margin-start', 0)
        bp.add_setter(self._hero, 'margin-end', 0)
        bp.add_setter(self._hero, 'margin-top', 0)
        bp.add_setter(self._header, 'margin-start', 24)
        bp.add_setter(self._header, 'margin-end', 24)
        bp.add_setter(self._header, 'margin-top', 128)
        bp.add_setter(self._header, 'margin-bottom', 24)
        self._narrow_mode = False
        bp.connect('apply', self._on_bp_apply)
        bp.connect('unapply', self._on_bp_unapply)
        bp_bin.add_breakpoint(bp)

        self._toolbar.set_content(bp_bin)
        self.set_child(self._toolbar)

        # Pre-set toolbar style from parent window size before animation
        self.connect('realize', self._on_realize)

    def _populate_episodes(self):
        while child := self._episodes_list.get_first_child():
            self._episodes_list.remove(child)

        for episode in self._release.episodes:
            row = Adw.ActionRow(
                title=self._episode_title(episode),
                subtitle=self._episode_subtitle(episode),
                activatable=True,
            )
            play_btn = Gtk.Button(
                icon_name='media-playback-start-symbolic',
                valign=Gtk.Align.CENTER,
                css_classes=['flat'],
            )
            play_btn.connect('clicked', self._on_play_clicked, episode)
            row.add_suffix(play_btn)
            row.connect('activated', lambda _r, ep=episode: self._play_episode(ep))
            self._episodes_list.append(row)

    def _episode_title(self, episode: Episode) -> str:
        ordinal = int(episode.ordinal) if episode.ordinal == int(episode.ordinal) else episode.ordinal
        if episode.name:
            return f'{ordinal}. {episode.name}'
        return _('Episode {}').format(ordinal)

    def _episode_subtitle(self, episode: Episode) -> str:
        parts = []
        if episode.duration:
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
        return ' — '.join(parts) if parts else ''

    def _on_play_clicked(self, _button, episode):
        self._play_episode(episode)

    def _play_episode(self, episode: Episode):
        if self._on_episode_play:
            self._on_episode_play(self._release, episode)

    def _on_bp_apply(self, _bp):
        self._narrow_mode = True
        self._update_toolbar()

    def _on_bp_unapply(self, _bp):
        self._narrow_mode = False
        self._update_toolbar()

    def _on_realize(self, _widget):
        root = self.get_root()
        if root and root.get_width() <= 500:
            self._narrow_mode = True
            self._toolbar.set_top_bar_style(Adw.ToolbarStyle.FLAT)
            self._toolbar.set_extend_content_to_top_edge(True)

    def _update_toolbar(self):
        if not self._narrow_mode:
            self._toolbar.set_top_bar_style(Adw.ToolbarStyle.FLAT)
            self._toolbar.set_extend_content_to_top_edge(False)
            return
        if self._vadjustment.get_value() > 50:
            self._toolbar.set_top_bar_style(Adw.ToolbarStyle.RAISED)
            self._toolbar.set_extend_content_to_top_edge(False)
        else:
            self._toolbar.set_top_bar_style(Adw.ToolbarStyle.FLAT)
            self._toolbar.set_extend_content_to_top_edge(True)

    def _on_scroll(self, _adjustment):
        self._update_toolbar()
        self._update_header_title()

    def _update_header_title(self):
        hero_h = self._hero.get_height()
        if hero_h > 0 and self._vadjustment.get_value() > hero_h:
            self.set_title(self._release.name.main)
        else:
            self.set_title('')

    def _on_genre_clicked(self, _button):
        dialog = Adw.AlertDialog(
            heading=_('Genre'),
            body=_('This feature is under development'),
        )
        dialog.add_response('ok', _('OK'))
        dialog.present(self.get_root())

    @staticmethod
    def _meta_row(label, value):
        row = Gtk.Box(spacing=8)
        row.append(Gtk.Label(
            label=f'{label}:',
            css_classes=['dim-label'],
            xalign=0,
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

    def _load_poster(self, url: str):
        load_image(url, self._on_poster_loaded)

    def _on_poster_loaded(self, texture, error):
        if texture:
            self._poster.set_paintable(texture)
            self._bg_poster.set_paintable(texture)
            # Match card height to image aspect ratio — no cropping
            w = texture.get_width()
            h = texture.get_height()
            if w > 0:
                self._poster.set_size_request(250, int(250 * h / w))
