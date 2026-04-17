# SPDX-License-Identifier: GPL-3.0-or-later

"""Widget tests for SessionExpiredBanner — require xvfb + compiled gresource."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from kitsune.ui.session_expired_banner import SessionExpiredBanner


def test_banner_starts_hidden():
    banner = SessionExpiredBanner()
    assert banner.get_reveal_child() is False


def test_banner_reveal_shows_widget():
    banner = SessionExpiredBanner()
    banner.set_reveal_child(True)
    assert banner.get_reveal_child() is True


def test_dismiss_sets_flag_and_hides():
    banner = SessionExpiredBanner()
    banner.set_reveal_child(True)
    assert not banner.dismissed_this_session
    # Simulate dismiss_btn click via the handler
    banner.on_dismiss_clicked(banner.dismiss_btn)
    assert banner.dismissed_this_session is True
    assert banner.get_reveal_child() is False


def test_reset_dismissal_clears_flag():
    banner = SessionExpiredBanner()
    banner.on_dismiss_clicked(banner.dismiss_btn)
    assert banner.dismissed_this_session is True
    banner.reset_dismissal()
    assert banner.dismissed_this_session is False


def test_login_clicked_fires_callback():
    banner = SessionExpiredBanner()
    fired = []
    banner.on_login_requested = lambda b: fired.append(b)
    banner.on_login_clicked(banner.login_btn)
    assert fired == [banner]


def test_dismiss_clicked_fires_callback():
    banner = SessionExpiredBanner()
    fired = []
    banner.on_dismissed = lambda b: fired.append(b)
    banner.on_dismiss_clicked(banner.dismiss_btn)
    assert fired == [banner]
