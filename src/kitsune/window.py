# SPDX-License-Identifier: GPL-3.0-or-later

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gdk, Gtk, Gio

from kitsune import ADW_TRANSITION
from kitsune.api import AniLibriaClient

_nav_css_loaded = False


def _ensure_nav_css():
    global _nav_css_loaded
    if _nav_css_loaded:
        return
    _nav_css_loaded = True
    css = Gtk.CssProvider()
    _T = ADW_TRANSITION
    css.load_from_string(
        '.nav-tab { background: none;'
        ' border-radius: 12px; padding: 6px 16px; min-width: 64px;'
        ' transition: background ' + _T + '; }'
        ' .nav-tab:hover { background: alpha(currentColor, 0.07); }'
        ' .nav-tab-active { background: alpha(currentColor, 0.1); }'
        ' .nav-tab-active:hover { background: alpha(currentColor, 0.14); }'
    )
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), css,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
from kitsune.ui.catalog_view import CatalogView


@Gtk.Template(resource_path='/net/armatik/Kitsune/window.ui')
class KitsuneWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'KitsuneWindow'

    nav_view = Gtk.Template.Child()
    offline_banner = Gtk.Template.Child()
    multi = Gtk.Template.Child()
    content_stack = Gtk.Template.Child()
    filter_btn = Gtk.Template.Child()
    sidebar_list = Gtk.Template.Child()
    wide_content_title = Gtk.Template.Child()
    back_btn = Gtk.Template.Child()
    narrow_back_btn = Gtk.Template.Child()
    narrow_catalog_tab = Gtk.Template.Child()
    narrow_genres_tab = Gtk.Template.Child()
    narrow_franchises_tab = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client = AniLibriaClient()
        self._client.set_on_network_error(self._on_network_error)
        self._client.set_on_network_ok(self._on_network_ok)
        self._settings = Gio.Settings(schema_id='net.armatik.Kitsune')
        _ensure_nav_css()
        self._active_player = None
        self._setup_window_state()
        self._setup_actions()
        self._setup_views()
        self.nav_view.connect('popped', self._on_nav_popped)

    def _setup_window_state(self):
        self.set_default_size(
            self._settings.get_int('window-width'),
            self._settings.get_int('window-height'),
        )
        self.connect('close-request', self._on_close_request)

    def _on_close_request(self, _window):
        self._stop_active_player()
        size = self.get_default_size()
        self._settings.set_int('window-width', size[0])
        self._settings.set_int('window-height', size[1])

    def _setup_actions(self):
        prefs_action = Gio.SimpleAction.new('preferences', None)
        prefs_action.connect('activate', self._on_preferences)
        self.add_action(prefs_action)

    def _setup_views(self):
        self._narrow = False
        self._genres_view = None
        self._franchises_view = None

        self._catalog_view = CatalogView(client=self._client)
        self._catalog_view.set_on_release_activated(self._show_release_detail)
        self.content_stack.add_named(self._catalog_view, 'catalog')

        for name in ('genres', 'franchises'):
            box = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
            box.append(Adw.Spinner(width_request=48, height_request=48))
            self.content_stack.add_named(box, name)

        self.sidebar_list.select_row(self.sidebar_list.get_row_at_index(0))

    def _create_genres_view(self):
        if self._genres_view:
            return
        from kitsune.ui.genres_view import GenresView
        old = self.content_stack.get_child_by_name('genres')
        self.content_stack.remove(old)
        self._genres_view = GenresView(client=self._client)
        self._genres_view.set_on_release_activated(self._show_release_detail)
        self._genres_view.set_on_navigation_changed(self._on_sub_navigation_changed)
        self._genres_view.set_narrow(self._narrow)
        self.content_stack.add_named(self._genres_view, 'genres')

    def _create_franchises_view(self):
        if self._franchises_view:
            return
        from kitsune.ui.franchises_view import FranchisesView
        old = self.content_stack.get_child_by_name('franchises')
        self.content_stack.remove(old)
        self._franchises_view = FranchisesView(client=self._client)
        self._franchises_view.set_on_release_activated(self._show_release_detail)
        self._franchises_view.set_on_navigation_changed(self._on_sub_navigation_changed)
        self._franchises_view.set_narrow(self._narrow)
        self.content_stack.add_named(self._franchises_view, 'franchises')

    # --- Template Callbacks ---

    @Gtk.Template.Callback()
    def on_filter_clicked(self, _button):
        self._catalog_view.open_filter_dialog()

    @Gtk.Template.Callback()
    def on_search_clicked(self, _button):
        dialog = Adw.AlertDialog(
            heading=_('Search'),
            body=_('This feature is under development'),
        )
        dialog.add_response('ok', _('OK'))
        dialog.present(self)

    @Gtk.Template.Callback()
    def on_back_clicked(self, _button):
        tab = self.content_stack.get_visible_child_name()
        if tab == 'genres' and self._genres_view:
            self._genres_view.go_back()
        elif tab == 'franchises' and self._franchises_view:
            self._franchises_view.go_back()
        self._update_content_header()

    @Gtk.Template.Callback()
    def on_sidebar_row_selected(self, listbox, row):
        if not row:
            return
        index = row.get_index()
        tabs = ['catalog', 'genres', 'franchises']
        if 0 <= index < len(tabs):
            self._switch_tab(tabs[index])

    @Gtk.Template.Callback()
    def on_catalog_tab_clicked(self, _button):
        self._switch_tab('catalog')

    @Gtk.Template.Callback()
    def on_genres_tab_clicked(self, _button):
        self._switch_tab('genres')

    @Gtk.Template.Callback()
    def on_franchises_tab_clicked(self, _button):
        self._switch_tab('franchises')

    @Gtk.Template.Callback()
    def on_narrow_apply(self, _bp):
        self._narrow = True
        self._catalog_view.set_narrow(True)
        if self._genres_view:
            self._genres_view.set_narrow(True)
        if self._franchises_view:
            self._franchises_view.set_narrow(True)

    @Gtk.Template.Callback()
    def on_narrow_unapply(self, _bp):
        self._narrow = False
        self._catalog_view.set_narrow(False)
        if self._genres_view:
            self._genres_view.set_narrow(False)
        if self._franchises_view:
            self._franchises_view.set_narrow(False)

    # --- Internal Methods ---

    def _switch_tab(self, name: str):
        if self._genres_view and self._genres_view.in_releases:
            self._genres_view.go_back()
        if self._franchises_view and self._franchises_view.in_releases:
            self._franchises_view.go_back()
        if name == 'genres':
            self._create_genres_view()
        elif name == 'franchises':
            self._create_franchises_view()
        self.content_stack.set_visible_child_name(name)
        self._update_content_header()
        self._update_nav_tabs(name)

    def _update_nav_tabs(self, active: str):
        tabs = {
            'catalog': self.narrow_catalog_tab,
            'genres': self.narrow_genres_tab,
            'franchises': self.narrow_franchises_tab,
        }
        for name, btn in tabs.items():
            if name == active:
                btn.add_css_class('nav-tab-active')
            else:
                btn.remove_css_class('nav-tab-active')

    def _update_content_header(self):
        tab = self.content_stack.get_visible_child_name()
        show_back = False
        titles = {
            'catalog': _('Catalog'),
            'genres': _('Genres'),
            'franchises': _('Franchises'),
        }
        title = titles.get(tab, '')

        if tab == 'genres' and self._genres_view and self._genres_view.in_releases:
            title = self._genres_view.current_genre_name
            show_back = True
        elif tab == 'franchises' and self._franchises_view and self._franchises_view.in_releases:
            title = self._franchises_view.current_franchise_name
            show_back = True

        show_filter = (tab == 'catalog')

        self.wide_content_title.set_title(title)
        self.back_btn.set_visible(show_back)
        self.narrow_back_btn.set_visible(show_back)
        self.filter_btn.set_visible(show_filter)

    def _on_sub_navigation_changed(self):
        self._update_content_header()

    def _on_preferences(self, _action, _param):
        from kitsune.ui.preferences_window import PreferencesWindow
        prefs = PreferencesWindow()
        prefs.present(self)

    def _show_release_detail(self, release):
        from kitsune.ui.release_view import ReleaseView
        view = ReleaseView(release=release, client=self._client)
        view.set_on_episode_play(self._play_episode)
        self.nav_view.push(view)

    def _on_network_error(self):
        self.offline_banner.set_revealed(True)

    def _on_network_ok(self):
        self.offline_banner.set_revealed(False)

    @Gtk.Template.Callback()
    def on_retry(self, _banner):
        tab = self.content_stack.get_visible_child_name()
        if tab == 'catalog':
            self._catalog_view.retry()
        elif tab == 'genres' and self._genres_view:
            self._genres_view.retry()
        elif tab == 'franchises' and self._franchises_view:
            self._franchises_view.retry()

    def _on_nav_popped(self, _nav_view, page):
        self._stop_active_player()

    def _stop_active_player(self):
        if self._active_player:
            player = self._active_player
            self._active_player = None
            player.cleanup()

    def _play_episode(self, release, episode):
        from kitsune.ui.player_view import PlayerView
        view = PlayerView(release=release, episode=episode)
        self._active_player = view._player
        self.nav_view.push(view)
