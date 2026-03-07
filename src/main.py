#!@PYTHON@
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import sys
import signal
import locale
import gettext

VERSION = '@VERSION@'
pkgdatadir = '@PKGDATADIR@'
localedir = '@LOCALEDIR@'

sys.path.insert(1, pkgdatadir)
signal.signal(signal.SIGINT, signal.SIG_DFL)

locale.bindtextdomain('kitsune', localedir)
locale.textdomain('kitsune')
gettext.install('kitsune', localedir)

if __name__ == '__main__':
    import logging
    if '--debug' in sys.argv:
        logging.basicConfig(level=logging.DEBUG, format='%(name)s: %(message)s')
        sys.argv.remove('--debug')
    else:
        logging.basicConfig(level=logging.WARNING)

    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Adw', '1')
    gi.require_version('Soup', '3.0')
    gi.require_version('Gst', '1.0')

    from gi.repository import Gio, Gst
    Gst.init(None)

    resource = Gio.Resource.load(os.path.join(pkgdatadir, 'net.armatik.Kitsune.gresource'))
    Gio.resources_register(resource)

    from kitsune.application import KitsuneApplication
    sys.exit(KitsuneApplication(version=VERSION).run(sys.argv))
