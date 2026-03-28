# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gtk

from kitsune import tags_store

_COLLECTION_TAGS = [
    ('favorites', 'Favorites'),
    ('watching', 'Watching'),
    ('watched', 'Watched'),
    ('planned', 'Planned'),
    ('postponed', 'Postponed'),
    ('abandoned', 'Abandoned'),
]


@Gtk.Template(resource_path='/net/armatik/Kitsune/profile_view.ui')
class ProfileView(Gtk.Box):
    __gtype_name__ = 'KitsuneProfileView'

    avatar = Gtk.Template.Child()
    nickname_label = Gtk.Template.Child()
    email_label = Gtk.Template.Child()
    sync_time_row = Gtk.Template.Child()
    sync_now_row = Gtk.Template.Child()
    collections_group = Gtk.Template.Child()
    total_label = Gtk.Template.Child()
    logout_button = Gtk.Template.Child()

    def __init__(self, session_manager, on_navigate_tag, sync_manager=None, **kwargs):
        super().__init__(**kwargs)
        self._session = session_manager
        self._on_navigate_tag = on_navigate_tag
        self._sync_manager = sync_manager
        self._count_labels = {}
        self._setup_collection_rows()

    def _setup_collection_rows(self):
        for tag_id, label in _COLLECTION_TAGS:
            row = Adw.ActionRow(
                title=_(label),
                activatable=True,
            )

            count_label = Gtk.Label(
                label='0',
                css_classes=['dim-label'],
                valign=Gtk.Align.CENTER,
            )
            row.add_suffix(count_label)
            self._count_labels[tag_id] = count_label

            icon = Gtk.Image(
                icon_name='go-next-symbolic',
                valign=Gtk.Align.CENTER,
            )
            row.add_suffix(icon)

            row.connect('activated', self._on_collection_activated, tag_id)
            self.collections_group.add(row)

    def _on_collection_activated(self, _row, tag_id):
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
        total = 0
        for tag_id, _label in _COLLECTION_TAGS:
            ids = tags_store.get_release_ids_for_tag(tag_id)
            count = len(ids)
            total += count
            label_widget = self._count_labels.get(tag_id)
            if label_widget:
                label_widget.set_label(str(count))
        self.total_label.set_label(str(total))

    def set_sync_time(self, time_str):
        self.sync_time_row.set_subtitle(time_str or _('No data'))

    @Gtk.Template.Callback()
    def on_sync_clicked(self, _row):
        if self._sync_manager:
            self._sync_manager.sync_now(self._on_sync_done)

    def _on_sync_done(self, ok, error):
        import datetime
        self.set_sync_time(datetime.datetime.now().strftime('%H:%M'))
        self.refresh_counts()

    @Gtk.Template.Callback()
    def on_settings_site_clicked(self, _row):
        launcher = Gtk.UriLauncher(uri='https://anilibria.top/app/settings/')
        launcher.launch(self.get_root(), None, None)

    @Gtk.Template.Callback()
    def on_logout_clicked(self, _button):
        if self._session:
            self._session.logout()
