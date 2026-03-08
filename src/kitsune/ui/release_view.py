# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from kitsune.api import AniLibriaClient
from kitsune.models import Release, Episode
from kitsune.ui.image_cache import load_image

_log = logging.getLogger('kitsune.release_view')

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
    episodes_spinner = Gtk.Template.Child()
    episodes_list = Gtk.Template.Child()
    gradient_bg = Gtk.Template.Child()

    def __init__(self, release: Release, client: AniLibriaClient, **kwargs):
        super().__init__(title=release.name.main, **kwargs)
        self._release = release
        self._client = client
        self._on_episode_play = None
        self._narrow_mode = False
        self._fade_anim = None
        self._accent_mode = False
        _ensure_css()

        self._settings = Gio.Settings(schema_id='net.armatik.Kitsune')

        self._vadjustment = self.scrolled.get_vadjustment()
        self._vadjustment.connect('value-changed', self._on_scroll)

        self._populate_info()

        if release.poster:
            self._load_poster(release.poster)
        if not release.episodes:
            self._load_full_release()
        else:
            self._populate_episodes()

        self.connect('realize', self._on_realize)

    def set_on_episode_play(self, callback):
        self._on_episode_play = callback

    def _populate_info(self):
        title_label = Gtk.Label(
            label=self._release.name.main,
            wrap=True, xalign=0, css_classes=['title-1'],
        )
        self.info_box.append(title_label)

        if self._release.name.english:
            en_label = Gtk.Label(
                label=self._release.name.english,
                wrap=True, xalign=0, css_classes=['dim-label'],
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
                btn.connect('clicked', self._on_genre_clicked)
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

    def _load_full_release(self):
        self.episodes_spinner.set_visible(True)
        self._client.get_release(
            self._release.alias or str(self._release.id),
            callback=self._on_release_loaded,
        )

    def _on_release_loaded(self, release, error):
        self.episodes_spinner.set_visible(False)
        if error or not release:
            return
        self._release = release
        self._populate_episodes()

    def _populate_episodes(self):
        while child := self.episodes_list.get_first_child():
            self.episodes_list.remove(child)

        for episode in self._release.episodes:
            row = Adw.ActionRow(
                title=self._episode_title(episode),
                subtitle=self._episode_subtitle(episode),
                activatable=True,
            )
            play_btn = Gtk.Button(
                icon_name='media-playback-start-symbolic',
                valign=Gtk.Align.CENTER, css_classes=['flat'],
            )
            play_btn.connect('clicked', self._on_play_clicked, episode)
            row.add_suffix(play_btn)
            row.connect('activated', lambda _r, ep=episode: self._play_episode(ep))
            self.episodes_list.append(row)

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

    @Gtk.Template.Callback()
    def on_bp_apply(self, _bp):
        self._narrow_mode = True
        self._update_toolbar()

    @Gtk.Template.Callback()
    def on_bp_unapply(self, _bp):
        self._narrow_mode = False
        self._update_toolbar()

    def _on_realize(self, _widget):
        root = self.get_root()
        if root and root.get_width() <= 500:
            self._narrow_mode = True
            self.toolbar.set_top_bar_style(Adw.ToolbarStyle.FLAT)
            self.toolbar.set_extend_content_to_top_edge(True)

    def _update_toolbar(self):
        if not self._narrow_mode:
            self.toolbar.set_top_bar_style(Adw.ToolbarStyle.FLAT)
            self.toolbar.set_extend_content_to_top_edge(False)
            return
        if self._vadjustment.get_value() > 50:
            self.toolbar.set_top_bar_style(Adw.ToolbarStyle.RAISED)
            self.toolbar.set_extend_content_to_top_edge(False)
        else:
            self.toolbar.set_top_bar_style(Adw.ToolbarStyle.FLAT)
            self.toolbar.set_extend_content_to_top_edge(True)

    def _on_scroll(self, _adjustment):
        self._update_toolbar()
        self._update_header_title()

    def _update_header_title(self):
        hero_h = self.hero.get_height()
        show = hero_h > 0 and self._vadjustment.get_value() > hero_h
        self.header_bar.set_show_title(show)

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

    def _load_poster(self, url: str):
        load_image(url, self._on_poster_loaded)

    def _on_poster_loaded(self, texture, error):
        _log.debug('Poster loaded: texture=%s, error=%s', texture, error)
        if texture:
            self.poster.set_paintable(texture)
            self.bg_poster.set_paintable(texture)
            w = texture.get_width()
            h = texture.get_height()
            _log.debug('Poster size: %dx%d', w, h)
            if w > 0:
                self.poster.set_size_request(250, int(250 * h / w))
            self._apply_page_style(texture)

    def _apply_page_style(self, texture: Gdk.Texture):
        style = self._settings.get_string('release-page-style')
        _log.debug('Release page style setting: %r', style)
        if style != 'accent':
            return

        from kitsune.ui.color_extractor import extract_colors, create_gradient_texture

        colors = extract_colors(texture)
        n_points = self._settings.get_int('accent-color-points')
        _log.debug('Extracted %d colors, using %d points: %s', len(colors), n_points, colors)

        glass = self._settings.get_boolean('accent-glass-effect')
        gradient = create_gradient_texture(colors, n_points=n_points, noise=glass)
        self.gradient_bg.set_paintable(gradient)
        self._accent_mode = True

        GLib.idle_add(self._start_gradient_fade)
        _log.debug('Set gradient paintable, fade scheduled')

    def _start_gradient_fade(self):
        duration = self._settings.get_int('accent-fade-duration')
        target = Adw.PropertyAnimationTarget.new(self.gradient_bg, 'opacity')
        self._fade_anim = Adw.TimedAnimation.new(self.gradient_bg, 0, 0.3, duration, target)
        self._fade_anim.play()
        _log.debug('Gradient fade-in started, duration=%dms', duration)
        return GLib.SOURCE_REMOVE

    def do_unmap(self):
        if self._fade_anim:
            self._fade_anim.skip()
            self._fade_anim = None
        Adw.NavigationPage.do_unmap(self)
