# SPDX-License-Identifier: GPL-3.0-or-later

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gdk, Gtk, Gio

from kitsune.api import AniLibriaClient

_nav_css_loaded = False


def _ensure_nav_css():
    global _nav_css_loaded
    if _nav_css_loaded:
        return
    _nav_css_loaded = True
    css = Gtk.CssProvider()
    css.load_from_string(
        '.nav-tab { background: none;'
        ' border-radius: 12px; padding: 6px 16px; min-width: 64px; }'
        ' .nav-tab:hover { background: alpha(currentColor, 0.07); }'
        ' .nav-tab-active { background: alpha(currentColor, 0.1); }'
        ' .nav-tab-active:hover { background: alpha(currentColor, 0.14); }'
    )
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), css,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
from kitsune.ui.catalog_view import CatalogView
from kitsune.ui.franchises_view import FranchisesView
from kitsune.ui.genres_view import GenresView
from kitsune.ui.release_view import ReleaseView
from kitsune.ui.player_view import PlayerView
from kitsune.ui.preferences_window import PreferencesWindow


class KitsuneWindow(Adw.ApplicationWindow):

    def __init__(self, **kwargs):
        super().__init__(
            default_width=900,
            default_height=600,
            **kwargs,
        )
        self._client = AniLibriaClient()
        self._settings = Gio.Settings(schema_id='net.armatik.Kitsune')
        _ensure_nav_css()
        self._setup_window_state()
        self._setup_actions()
        self._build_ui()

    def _setup_window_state(self):
        self.set_default_size(
            self._settings.get_int('window-width'),
            self._settings.get_int('window-height'),
        )
        self.connect('close-request', self._on_close_request)

    def _on_close_request(self, _window):
        size = self.get_default_size()
        self._settings.set_int('window-width', size[0])
        self._settings.set_int('window-height', size[1])

    def _setup_actions(self):
        prefs_action = Gio.SimpleAction.new('preferences', None)
        prefs_action.connect('activate', self._on_preferences)
        self.add_action(prefs_action)

    def _build_ui(self):
        self._nav_view = Adw.NavigationView()
        self.set_content(self._nav_view)

        main_page = Adw.NavigationPage(title='Kitsune', tag='main')

        # MultiLayoutView: shared children move between layouts via slots
        self._multi = Adw.MultiLayoutView()

        # Content stack: catalog + genres
        self._stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)

        self._catalog_view = CatalogView(client=self._client)
        self._catalog_view.set_on_release_activated(self._show_release_detail)
        self._stack.add_named(self._catalog_view, 'catalog')

        self._genres_view = GenresView(client=self._client)
        self._genres_view.set_on_release_activated(self._show_release_detail)
        self._genres_view.set_on_navigation_changed(self._on_sub_navigation_changed)
        self._stack.add_named(self._genres_view, 'genres')

        self._franchises_view = FranchisesView(client=self._client)
        self._franchises_view.set_on_release_activated(self._show_release_detail)
        self._franchises_view.set_on_navigation_changed(self._on_sub_navigation_changed)
        self._stack.add_named(self._franchises_view, 'franchises')

        self._multi.set_child('content', self._stack)

        # Shared child: filter button (appears in both layout headers)
        self._filter_btn = Gtk.Button(
            icon_name='funnel-symbolic',
            tooltip_text=_('Filters'),
        )
        self._filter_btn.connect('clicked', self._on_filter_clicked)
        self._multi.set_child('filter', self._filter_btn)

        # Add layouts
        self._multi.add_layout(self._build_wide_layout())
        self._multi.add_layout(self._build_narrow_layout())

        # Breakpoint: narrow mode
        bp = Adw.Breakpoint.new(
            Adw.BreakpointCondition.parse('max-width: 650sp'),
        )
        bp.add_setter(self._multi, 'layout-name', 'narrow')
        bp.connect('apply', self._on_narrow_apply)
        bp.connect('unapply', self._on_narrow_unapply)
        self.add_breakpoint(bp)

        main_page.set_child(self._multi)
        self._nav_view.push(main_page)

    def _build_wide_layout(self):
        split = Adw.OverlaySplitView()
        split.set_collapsed(False)

        # Sidebar (layout-specific, not a slot)
        sidebar_toolbar = Adw.ToolbarView()
        sidebar_header = Adw.HeaderBar()
        sidebar_header.set_title_widget(Adw.WindowTitle(title='Kitsune'))

        search_btn = Gtk.Button(
            icon_name='system-search-symbolic',
            tooltip_text=_('Search'),
        )
        search_btn.connect('clicked', self._on_search_clicked)
        sidebar_header.pack_start(search_btn)

        menu = Gio.Menu()
        menu.append(_('Preferences'), 'win.preferences')
        menu.append(_('About Kitsune'), 'app.about')
        menu_btn = Gtk.MenuButton(
            icon_name='open-menu-symbolic',
            menu_model=menu,
            tooltip_text=_('Main Menu'),
            primary=True,
        )
        sidebar_header.pack_end(menu_btn)
        sidebar_toolbar.add_top_bar(sidebar_header)

        sidebar_list = Gtk.ListBox(css_classes=['navigation-sidebar'])
        sidebar_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        catalog_row = Adw.ActionRow(
            title=_('Catalog'), icon_name='view-grid-symbolic',
        )
        sidebar_list.append(catalog_row)
        genres_row = Adw.ActionRow(
            title=_('Genres'), icon_name='genres-symbolic',
        )
        sidebar_list.append(genres_row)
        franchises_row = Adw.ActionRow(
            title=_('Franchises'), icon_name='franchises-symbolic',
        )
        sidebar_list.append(franchises_row)
        sidebar_list.select_row(sidebar_list.get_row_at_index(0))
        sidebar_list.connect('row-selected', self._on_sidebar_row_selected)
        sidebar_toolbar.set_content(sidebar_list)

        split.set_sidebar(sidebar_toolbar)

        # Content column
        self._wide_content_toolbar = Adw.ToolbarView()
        self._wide_content_header = Adw.HeaderBar()
        self._wide_content_title = Adw.WindowTitle(title=_('Catalog'))
        self._wide_content_header.set_title_widget(self._wide_content_title)

        self._back_btn = Gtk.Button(
            icon_name='go-previous-symbolic',
            tooltip_text=_('Back'),
            visible=False,
        )
        self._back_btn.connect('clicked', self._on_back_clicked)
        self._wide_content_header.pack_start(self._back_btn)

        filter_slot = Adw.LayoutSlot.new('filter')
        self._wide_content_header.pack_end(filter_slot)
        self._wide_content_toolbar.add_top_bar(self._wide_content_header)

        content_slot = Adw.LayoutSlot.new('content')
        self._wide_content_toolbar.set_content(content_slot)

        split.set_content(self._wide_content_toolbar)
        return Adw.Layout(name='wide', content=split)

    def _build_narrow_layout(self):
        toolbar = Adw.ToolbarView()

        # Header with all buttons
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title='Kitsune'))

        self._narrow_back_btn = Gtk.Button(
            icon_name='go-previous-symbolic',
            tooltip_text=_('Back'),
            visible=False,
        )
        self._narrow_back_btn.connect('clicked', self._on_back_clicked)
        header.pack_start(self._narrow_back_btn)

        search_btn = Gtk.Button(
            icon_name='system-search-symbolic',
            tooltip_text=_('Search'),
        )
        search_btn.connect('clicked', self._on_search_clicked)
        header.pack_start(search_btn)

        menu = Gio.Menu()
        menu.append(_('Preferences'), 'win.preferences')
        menu.append(_('About Kitsune'), 'app.about')
        menu_btn = Gtk.MenuButton(
            icon_name='open-menu-symbolic',
            menu_model=menu,
            tooltip_text=_('Main Menu'),
            primary=True,
        )
        header.pack_end(menu_btn)

        filter_slot = Adw.LayoutSlot.new('filter')
        header.pack_end(filter_slot)

        toolbar.add_top_bar(header)

        # Content (shared slot)
        content_slot = Adw.LayoutSlot.new('content')
        toolbar.set_content(content_slot)

        # Bottom navigation bar
        bottom_bar = Gtk.CenterBox(css_classes=['toolbar'])
        nav_box = Gtk.Box(
            halign=Gtk.Align.CENTER,
            spacing=24,
            margin_top=4,
            margin_bottom=4,
        )

        self._narrow_catalog_tab = Gtk.Button(css_classes=['flat', 'nav-tab', 'nav-tab-active'])
        catalog_tab_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=2,
            halign=Gtk.Align.CENTER,
        )
        catalog_tab_box.append(Gtk.Image(icon_name='view-grid-symbolic'))
        catalog_tab_box.append(Gtk.Label(label=_('Catalog'), css_classes=['caption']))
        self._narrow_catalog_tab.set_child(catalog_tab_box)
        self._narrow_catalog_tab.connect('clicked', lambda _b: self._switch_tab('catalog'))
        nav_box.append(self._narrow_catalog_tab)

        self._narrow_genres_tab = Gtk.Button(css_classes=['flat', 'nav-tab'])
        genres_tab_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=2,
            halign=Gtk.Align.CENTER,
        )
        genres_tab_box.append(Gtk.Image(icon_name='genres-symbolic'))
        genres_tab_box.append(Gtk.Label(label=_('Genres'), css_classes=['caption']))
        self._narrow_genres_tab.set_child(genres_tab_box)
        self._narrow_genres_tab.connect('clicked', lambda _b: self._switch_tab('genres'))
        nav_box.append(self._narrow_genres_tab)

        self._narrow_franchises_tab = Gtk.Button(css_classes=['flat', 'nav-tab'])
        franchises_tab_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=2,
            halign=Gtk.Align.CENTER,
        )
        franchises_tab_box.append(Gtk.Image(icon_name='franchises-symbolic'))
        franchises_tab_box.append(Gtk.Label(label=_('Franchises'), css_classes=['caption']))
        self._narrow_franchises_tab.set_child(franchises_tab_box)
        self._narrow_franchises_tab.connect('clicked', lambda _b: self._switch_tab('franchises'))
        nav_box.append(self._narrow_franchises_tab)

        bottom_bar.set_center_widget(nav_box)
        toolbar.add_bottom_bar(bottom_bar)

        return Adw.Layout(name='narrow', content=toolbar)

    # --- Callbacks ---

    def _on_narrow_apply(self, _bp):
        self._catalog_view.set_narrow(True)
        self._genres_view.set_narrow(True)
        self._franchises_view.set_narrow(True)

    def _on_narrow_unapply(self, _bp):
        self._catalog_view.set_narrow(False)
        self._genres_view.set_narrow(False)
        self._franchises_view.set_narrow(False)

    def _switch_tab(self, name: str):
        # Reset sub-navigation when switching tabs
        if self._genres_view.in_releases:
            self._genres_view.go_back()
        if self._franchises_view.in_releases:
            self._franchises_view.go_back()
        self._stack.set_visible_child_name(name)
        self._update_content_header()
        self._update_nav_tabs(name)

    def _update_nav_tabs(self, active: str):
        tabs = {
            'catalog': self._narrow_catalog_tab,
            'genres': self._narrow_genres_tab,
            'franchises': self._narrow_franchises_tab,
        }
        for name, btn in tabs.items():
            if name == active:
                btn.add_css_class('nav-tab-active')
            else:
                btn.remove_css_class('nav-tab-active')

    def _update_content_header(self):
        tab = self._stack.get_visible_child_name()
        show_back = False
        titles = {
            'catalog': _('Catalog'),
            'genres': _('Genres'),
            'franchises': _('Franchises'),
        }
        title = titles.get(tab, '')

        if tab == 'genres' and self._genres_view.in_releases:
            title = self._genres_view.current_genre_name
            show_back = True
        elif tab == 'franchises' and self._franchises_view.in_releases:
            title = self._franchises_view.current_franchise_name
            show_back = True

        show_filter = (tab == 'catalog')

        if hasattr(self, '_wide_content_title'):
            self._wide_content_title.set_title(title)
        if hasattr(self, '_back_btn'):
            self._back_btn.set_visible(show_back)
        if hasattr(self, '_narrow_back_btn'):
            self._narrow_back_btn.set_visible(show_back)
        if hasattr(self, '_filter_btn'):
            self._filter_btn.set_visible(show_filter)

    def _on_sidebar_row_selected(self, listbox, row):
        if not row:
            return
        index = row.get_index()
        tabs = ['catalog', 'genres', 'franchises']
        if 0 <= index < len(tabs):
            self._switch_tab(tabs[index])

    def _on_sub_navigation_changed(self):
        self._update_content_header()

    def _on_back_clicked(self, _button):
        tab = self._stack.get_visible_child_name()
        if tab == 'genres':
            self._genres_view.go_back()
        elif tab == 'franchises':
            self._franchises_view.go_back()
        self._update_content_header()

    def _on_filter_clicked(self, _button):
        self._catalog_view.open_filter_dialog()

    def _on_search_clicked(self, _button):
        dialog = Adw.AlertDialog(
            heading=_('Search'),
            body=_('This feature is under development'),
        )
        dialog.add_response('ok', _('OK'))
        dialog.present(self)

    def _on_preferences(self, _action, _param):
        prefs = PreferencesWindow()
        prefs.present(self)

    def _show_release_detail(self, release):
        view = ReleaseView(release=release, client=self._client)
        view.set_on_episode_play(self._play_episode)
        self._nav_view.push(view)

    def _play_episode(self, release, episode):
        view = PlayerView(release=release, episode=episode)
        self._nav_view.push(view)
