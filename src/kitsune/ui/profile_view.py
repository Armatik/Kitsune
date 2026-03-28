# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gtk

from kitsune import tags_store
from kitsune.ui import register_css

_COLLECTION_TAGS = [
    ('favorites', 'Favorites', '⭐', '#f5c211'),
    ('watching', 'Watching', '▶', '#9141ac'),
    ('watched', 'Watched', '✓', '#26a269'),
    ('planned', 'Planned', '📋', '#3584e4'),
    ('postponed', 'Postponed', '⏸', '#e66100'),
    ('abandoned', 'Abandoned', '✕', '#e01b24'),
]

_PROFILE_CSS = (
    '.profile-hero-bg { background:'
    ' linear-gradient(135deg, #e01b24 0%, #9141ac 100%); }'
    ' .profile-hero-gradient { background:'
    ' linear-gradient(to bottom, alpha(@window_bg_color, 0) 40%,'
    ' @window_bg_color 100%); }'
    ' .profile-hero-bg + .profile-hero-gradient + box label'
    ' { color: white; text-shadow: 0 1px 3px alpha(black, 0.3); }'
    ' .profile-content { margin-top: -60px; }'
    ' .collection-card { background: @card_bg_color;'
    ' border-radius: 12px; padding: 16px;'
    ' border: 1px solid alpha(currentColor, 0.08); }'
    ' .collection-card:hover { background: alpha(@accent_bg_color, 0.08); }'
    ' .collection-emoji { font-size: 24px; }'
    ' .collection-count { font-size: 22px; font-weight: bold; }'
)


@Gtk.Template(resource_path='/net/armatik/Kitsune/profile_view.ui')
class ProfileView(Gtk.Box):
    __gtype_name__ = 'KitsuneProfileView'

    avatar = Gtk.Template.Child()
    nickname_label = Gtk.Template.Child()
    email_label = Gtk.Template.Child()
    sync_time_label = Gtk.Template.Child()
    sync_button = Gtk.Template.Child()
    collections_flow = Gtk.Template.Child()
    logout_button = Gtk.Template.Child()

    def __init__(self, session_manager, on_navigate_tag, sync_manager=None, **kwargs):
        super().__init__(**kwargs)
        register_css(_PROFILE_CSS)
        self._session = session_manager
        self._on_navigate_tag = on_navigate_tag
        self._sync_manager = sync_manager
        self._cards = {}
        self._setup_collection_cards()

    def _setup_collection_cards(self):
        for tag_id, label, emoji, color in _COLLECTION_TAGS:
            count = len(tags_store.get_release_ids_for_tag(tag_id))

            card = Gtk.Button(css_classes=['flat'])
            card.connect('clicked', self._on_collection_clicked, tag_id)

            card_box = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=4,
                css_classes=['collection-card'],
            )

            # Emoji
            emoji_label = Gtk.Label(label=emoji, css_classes=['collection-emoji'])
            card_box.append(emoji_label)

            # Count
            count_label = Gtk.Label(
                label=str(count),
                css_classes=['collection-count'],
            )
            count_label.set_markup(
                f'<span color="{color}">{count}</span>'
            )
            card_box.append(count_label)

            # Title
            title_label = Gtk.Label(
                label=_(label),
                css_classes=['caption', 'dim-label'],
            )
            card_box.append(title_label)

            card.set_child(card_box)
            self.collections_flow.append(card)
            self._cards[tag_id] = count_label

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
            self.avatar.set_text('')
            return
        nickname = user.nickname or ''
        self.nickname_label.set_label(nickname)
        self.avatar.set_text(nickname)
        self.email_label.set_label(user.email or '')

    def refresh_counts(self):
        for tag_id, _label, _emoji, color in _COLLECTION_TAGS:
            ids = tags_store.get_release_ids_for_tag(tag_id)
            count = len(ids)
            label_widget = self._cards.get(tag_id)
            if label_widget:
                label_widget.set_markup(
                    f'<span color="{color}">{count}</span>'
                )

    def set_sync_time(self, time_str):
        self.sync_time_label.set_label(
            _('Synced at %s') % time_str if time_str else ''
        )

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
