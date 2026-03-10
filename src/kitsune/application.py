# SPDX-License-Identifier: GPL-3.0-or-later

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gio, GLib, Gtk

from kitsune import SITE_URL, API_BASE_URL
from kitsune.window import KitsuneWindow


class KitsuneApplication(Adw.Application):

    def __init__(self, version='0.1.0', **kwargs):
        super().__init__(
            application_id='net.armatik.Kitsune',
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
            **kwargs,
        )
        self._version = version

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = KitsuneWindow(application=self)
        win.present()

    def do_startup(self):
        Adw.Application.do_startup(self)

        about_action = Gio.SimpleAction.new('about', None)
        about_action.connect('activate', self._on_about)
        self.add_action(about_action)

        quit_action = Gio.SimpleAction.new('quit', None)
        quit_action.connect('activate', lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action('app.quit', ['<primary>q'])

    def _on_about(self, _action, _param):
        about = Adw.AboutDialog(
            application_name='Kitsune',
            application_icon='net.armatik.Kitsune',
            version=self._version,
            developer_name='Armatik',
            license_type=Gtk.License.GPL_3_0,
            website='https://altlinux.space/armatik/Kitsune',
            issue_url='https://altlinux.space/armatik/Kitsune/issues',
            comments=_('Libadwaita client for watching anime from AniLiberty'),
        )
        about.add_link(_('AniLiberty Website'), SITE_URL)
        about.add_link(_('AniLiberty Telegram'), 'https://t.me/anilibria')
        about.add_link(_('AniLiberty VK'), 'https://vk.com/anilibria')
        about.add_acknowledgement_section(
            _('Uses'),
            [f'AniLiberty API {API_BASE_URL.replace("/v1", "/docs/v1")}'],
        )
        about.present(self.props.active_window)
