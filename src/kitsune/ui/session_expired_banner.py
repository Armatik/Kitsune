# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging

import gi

gi.require_version('Gtk', '4.0')

from gi.repository import Gtk

log = logging.getLogger('kitsune.session_expired_banner')


@Gtk.Template(resource_path='/net/armatik/Kitsune/session_expired_banner.ui')
class SessionExpiredBanner(Gtk.Revealer):
    """Banner shown when the server rejected our token.

    Two callbacks the host wires via attribute assignment:
      - `on_login_requested(banner)` — user clicked "Log in again"
      - `on_dismissed(banner)` — user clicked the × button

    Host is expected to call `set_reveal_child(True)` when
    `session-expired` fires, and `set_reveal_child(False)` when
    `session-restored` or `logged-out` fires. Dismissal by the user
    sets `_dismissed_this_session = True` so host can skip re-showing
    within the current app run until a session-restored cycle
    explicitly re-enables via `reset_dismissal()`.
    """

    __gtype_name__ = 'KitsuneSessionExpiredBanner'

    login_btn = Gtk.Template.Child()
    dismiss_btn = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.on_login_requested = None
        self.on_dismissed = None
        self._dismissed_this_session = False

    @property
    def dismissed_this_session(self):
        return self._dismissed_this_session

    def reset_dismissal(self):
        """Allow the banner to reveal again after a session-restored
        cycle (so the next expiry is not auto-hidden)."""
        self._dismissed_this_session = False

    @Gtk.Template.Callback()
    def on_login_clicked(self, _button):
        if self.on_login_requested:
            self.on_login_requested(self)

    @Gtk.Template.Callback()
    def on_dismiss_clicked(self, _button):
        self._dismissed_this_session = True
        self.set_reveal_child(False)
        if self.on_dismissed:
            self.on_dismissed(self)
