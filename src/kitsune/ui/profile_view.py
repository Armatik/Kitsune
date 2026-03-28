# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
import random

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gdk, GLib, Gtk

from kitsune import tags_store
from kitsune.ui import register_css

log = logging.getLogger('kitsune.profile_view')

_COLLECTION_TAGS = [
    ('favorites', 'Favorites', '⭐', '#f5c211'),
    ('watching', 'Watching', '▶', '#9141ac'),
    ('watched', 'Watched', '✓', '#26a269'),
    ('planned', 'Planned', '📋', '#3584e4'),
    ('postponed', 'Postponed', '⏸', '#e66100'),
    ('abandoned', 'Abandoned', '✕', '#e01b24'),
]

# Hero images from AniLibria CDN
_HERO_IMAGES = [
    'SD01.BK-zeZze.jpg', 'SD02.CFb2ug4g.jpg', 'SD03.Big5uXdC.jpg',
    'SD04.iDB17XuA.jpg', 'SD05.xSIf8EKO.jpg', 'SD06.DzSKOZiB.jpg',
    'SD07.PUUEzIZh.jpg', 'SD08.D_N8GfOl.jpg', 'SD09.DdbN9Lh3.jpg',
    'SD10.CT9UJk16.jpg', 'SD11.CoQVRJh3.jpg', 'SD12.Py78cBAE.jpg',
    'SD13.6iC3GxuS.jpg', 'SD14.1vbAt3XX.jpg', 'SD15.DqhS0xIL.jpg',
    'SD16.Di6S4bdo.jpg', 'SD17.B1bzHyBh.jpg', 'SD18.COgz20JF.jpg',
    'SD19.DpTeEfyb.jpg', 'SD20.De4OAhxk.jpg', 'REG01.CktUHpfc.jpg',
    'REG02.CQ9KlpWV.jpg', 'REG03.CTS9TmSc.jpg', 'REG04.BDVfGboN.jpg',
]

_PROFILE_CSS = (
    # Card container
    ' .profile-card { background: @card_bg_color;'
    ' border-radius: 20px; overflow: hidden;'
    ' border: 1px solid alpha(currentColor, 0.06);'
    ' box-shadow: 0 4px 24px alpha(black, 0.15); }'
    # Hero gradient
    ' .profile-hero-gradient { background:'
    ' linear-gradient(to bottom, transparent 0%,'
    ' alpha(@card_bg_color, 0.25) 40%,'
    ' alpha(@card_bg_color, 0.65) 65%,'
    ' @card_bg_color 100%); }'
    # Avatar overlap
    ' .profile-avatar-box { margin-top: -44px; }'
    # Collection card
    ' .collection-card { border-radius: 14px; padding: 14px 8px;'
    ' border: 1px solid alpha(currentColor, 0.06); }'
    # Total card
    ' .total-card { border-radius: 12px; padding: 14px 16px;'
    ' background: alpha(@accent_bg_color, 0.08);'
    ' border: 1px solid alpha(@accent_bg_color, 0.10); }'
    # Remove flowbox child padding
    ' .profile-card flowboxchild { padding: 0; background: none; }'
)


def _hex_to_rgba(hex_color, alpha):
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return f'rgba({r},{g},{b},{alpha})'


@Gtk.Template(resource_path='/net/armatik/Kitsune/profile_view.ui')
class ProfileView(Gtk.Box):
    __gtype_name__ = 'KitsuneProfileView'

    profile_card = Gtk.Template.Child()
    hero_picture = Gtk.Template.Child()
    avatar = Gtk.Template.Child()
    nickname_label = Gtk.Template.Child()
    email_label = Gtk.Template.Child()
    member_since_label = Gtk.Template.Child()
    sync_time_label = Gtk.Template.Child()
    sync_button = Gtk.Template.Child()
    collections_flow = Gtk.Template.Child()
    totals_box = Gtk.Template.Child()
    logout_button = Gtk.Template.Child()

    def __init__(self, session_manager, on_navigate_tag, sync_manager=None, **kwargs):
        super().__init__(**kwargs)
        register_css(_PROFILE_CSS)
        self._session = session_manager
        self._on_navigate_tag = on_navigate_tag
        self._sync_manager = sync_manager
        self._cards = {}

        self._setup_collection_cards()
        self._setup_total_cards()
        self._load_hero_image()

    def _setup_collection_cards(self):
        for tag_id, label, emoji, color in _COLLECTION_TAGS:
            count = len(tags_store.get_release_ids_for_tag(tag_id))

            card_btn = Gtk.Button(css_classes=['flat'])
            card_btn.connect('clicked', self._on_collection_clicked, tag_id)

            bg_start = _hex_to_rgba(color, 0.10)
            bg_end = _hex_to_rgba(color, 0.03)
            border = _hex_to_rgba(color, 0.12)

            card_box = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=4,
                css_classes=['collection-card'],
            )
            css_provider = Gtk.CssProvider()
            css_provider.load_from_string(
                f'.collection-card {{ background:'
                f' linear-gradient(135deg, {bg_start}, {bg_end});'
                f' border-color: {border}; }}'
            )
            card_box.get_style_context().add_provider(
                css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

            emoji_lbl = Gtk.Label()
            emoji_lbl.set_markup(f'<span size="x-large">{emoji}</span>')
            card_box.append(emoji_lbl)

            count_lbl = Gtk.Label()
            count_lbl.set_markup(
                f'<span size="x-large" weight="bold" color="{color}">'
                f'{count}</span>')
            card_box.append(count_lbl)

            title_lbl = Gtk.Label(
                label=_(label),
                css_classes=['caption', 'dim-label'],
            )
            card_box.append(title_lbl)

            card_btn.set_child(card_box)
            self.collections_flow.append(card_btn)
            self._cards[tag_id] = count_lbl

    def _setup_total_cards(self):
        total = sum(
            len(tags_store.get_release_ids_for_tag(tid))
            for tid, _, _, _ in _COLLECTION_TAGS
        )

        box1 = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            halign=Gtk.Align.CENTER,
            css_classes=['total-card'],
        )
        self._total_label = Gtk.Label()
        self._total_label.set_markup(
            f'<span size="x-large" weight="bold">{total}</span>')
        box1.append(self._total_label)
        box1.append(Gtk.Label(
            label=_('Total titles'),
            css_classes=['caption', 'dim-label'],
        ))
        self.totals_box.append(box1)

        box2 = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            halign=Gtk.Align.CENTER,
            css_classes=['total-card'],
        )
        self._episodes_label = Gtk.Label()
        self._episodes_label.set_markup(
            '<span size="x-large" weight="bold">—</span>')
        box2.append(self._episodes_label)
        box2.append(Gtk.Label(
            label=_('Episodes watched'),
            css_classes=['caption', 'dim-label'],
        ))
        self.totals_box.append(box2)

    def _load_hero_image(self):
        from gi.repository import Soup

        name = random.choice(_HERO_IMAGES)
        url = f'https://cdn.anilibria.top/static/{name}'
        log.debug('Profile hero: loading %s', url)

        session = Soup.Session()
        msg = Soup.Message.new('GET', url)

        def on_image(_session, result):
            try:
                gbytes = _session.send_and_read_finish(result)
                if gbytes and gbytes.get_size() > 0:
                    texture = Gdk.Texture.new_from_bytes(gbytes)
                    self.hero_picture.set_paintable(texture)
                    self._fade_in_hero()
            except Exception as e:
                log.debug('Profile hero: failed: %s', e)

        session.send_and_read_async(msg, GLib.PRIORITY_DEFAULT, None, on_image)

    def _fade_in_hero(self):
        opacity = [0.0]

        def tick():
            opacity[0] = min(1.0, opacity[0] + 0.015)
            self.hero_picture.set_opacity(opacity[0])
            if opacity[0] >= 1.0:
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE

        GLib.timeout_add(16, tick)

    def _on_collection_clicked(self, _button, tag_id):
        if self._on_navigate_tag:
            data = tags_store._load()
            tag = tags_store._find_tag(data, tag_id)
            if tag:
                self._on_navigate_tag(tag)

    def update_profile(self, user):
        if user is None:
            self.nickname_label.set_label('')
            self.email_label.set_label('')
            self.member_since_label.set_label('')
            self.avatar.set_text('')
            return
        nickname = user.nickname or ''
        self.nickname_label.set_label(nickname)
        self.avatar.set_text(nickname)
        self.email_label.set_label(user.email or '')
        if user.created_at:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(
                    user.created_at.replace('Z', '+00:00'))
                self.member_since_label.set_label(
                    _('Member since %s') % dt.strftime('%B %Y'))
            except Exception:
                self.member_since_label.set_label('')

    def refresh_counts(self):
        total = 0
        for tag_id, _label, _emoji, color in _COLLECTION_TAGS:
            ids = tags_store.get_release_ids_for_tag(tag_id)
            count = len(ids)
            total += count
            lbl = self._cards.get(tag_id)
            if lbl:
                lbl.set_markup(
                    f'<span size="x-large" weight="bold" color="{color}">'
                    f'{count}</span>')
        self._total_label.set_markup(
            f'<span size="x-large" weight="bold">{total}</span>')

    def set_sync_time(self, time_str):
        self.sync_time_label.set_label(
            _('Synced at %s') % time_str if time_str else '')

    @Gtk.Template.Callback()
    def on_sync_clicked(self, _button):
        if self._sync_manager:
            self._sync_manager.sync_now(self._on_sync_done)

    def _on_sync_done(self, ok, error):
        import datetime
        self.set_sync_time(datetime.datetime.now().strftime('%H:%M'))
        self.refresh_counts()

    @Gtk.Template.Callback()
    def on_settings_site_clicked(self, _button):
        launcher = Gtk.UriLauncher(uri='https://anilibria.top/app/settings/')
        launcher.launch(self.get_root(), None, None)

    @Gtk.Template.Callback()
    def on_logout_clicked(self, _button):
        if self._session:
            self._session.logout()
