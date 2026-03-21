# SPDX-License-Identifier: GPL-3.0-or-later

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gdk, Gtk, Gio

from kitsune import ADW_TRANSITION
from kitsune.api import AniLibriaClient
from kitsune.navbar import get_tab, get_visible_tabs
from kitsune.ui import register_css
from kitsune.ui.catalog_view import CatalogView

_T = ADW_TRANSITION
_NAV_CSS = (
    '.nav-tab { background: none;'
    ' border-radius: 12px; padding: 6px 8px;'
    ' transition: background ' + _T + '; }'
    ' .nav-tab:hover { background: alpha(currentColor, 0.07); }'
    ' .nav-tab-active { background: alpha(currentColor, 0.1); }'
    ' .nav-tab-active:hover { background: alpha(currentColor, 0.14); }'
    ' .drag-handle-pill { background: alpha(currentColor, 0.25);'
    ' border-radius: 2px; }'
    ' .sheet-grid-item { padding: 8px 6px;'
    ' border-radius: 12px; }'
    ' .sheet-grid flowboxchild { background: none; }'
    ' .sheet-grid flowboxchild:hover { background: none; }'
    ' .sheet-grid flowboxchild:active { background: none; }'
)


@Gtk.Template(resource_path='/net/armatik/Kitsune/window.ui')
class KitsuneWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'KitsuneWindow'

    nav_view = Gtk.Template.Child()
    offline_banner = Gtk.Template.Child()
    multi = Gtk.Template.Child()
    content_stack = Gtk.Template.Child()
    filter_btn = Gtk.Template.Child()
    mode_btn = Gtk.Template.Child()
    add_tag_btn = Gtk.Template.Child()
    delete_tag_btn = Gtk.Template.Child()
    filter_split = Gtk.Template.Child()
    sidebar_list = Gtk.Template.Child()
    wide_content_title = Gtk.Template.Child()
    back_btn = Gtk.Template.Child()
    narrow_back_btn = Gtk.Template.Child()
    narrow_sheet = Gtk.Template.Child()
    narrow_bottom_bar = Gtk.Template.Child()
    narrow_drag_handle = Gtk.Template.Child()
    narrow_tabs_box = Gtk.Template.Child()
    narrow_sheet_box = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client = AniLibriaClient()
        self._client.set_on_network_error(self._on_network_error)
        self._client.set_on_network_ok(self._on_network_ok)
        self._settings = Gio.Settings(schema_id='net.armatik.Kitsune')
        register_css(_NAV_CSS)
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

        shortcut_ctrl = Gtk.ShortcutController()
        shortcut_ctrl.set_scope(Gtk.ShortcutScope.MANAGED)
        shortcut = Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string('<Control>f'),
            action=Gtk.CallbackAction.new(
                lambda *_: self._open_search_dialog() or True
            ),
        )
        shortcut_ctrl.add_shortcut(shortcut)
        self.add_controller(shortcut_ctrl)

    def _setup_views(self):
        self._narrow = False
        self._genres_view = None
        self._franchises_view = None
        self._tags_view = None
        self._sidebar_tab_ids = []

        self._catalog_view = CatalogView(client=self._client)
        self._catalog_view.set_on_release_activated(self._show_release_detail)
        self.content_stack.add_named(self._catalog_view, 'catalog')

        for name in ('genres', 'franchises', 'tags'):
            box = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
            box.append(Adw.Spinner(width_request=48, height_request=48))
            self.content_stack.add_named(box, name)

        self._narrow_tab_buttons = {}
        self._narrow_tab_ids = []
        self._drag_handle_gesture = None

        self._build_sidebar()
        self._build_bottom_bar()

        for key in ('navbar-desktop', 'navbar-mobile',
                    'navbar-sync', 'navbar-sheet-style'):
            self._settings.connect(
                f'changed::{key}', self._on_navbar_settings_changed)

    def _build_sidebar(self):
        """Populate sidebar from GSettings."""
        while True:
            row = self.sidebar_list.get_row_at_index(0)
            if row is None:
                break
            self.sidebar_list.remove(row)

        tab_ids = get_visible_tabs(self._settings, is_narrow=False)
        self._sidebar_tab_ids = tab_ids

        _TAB_LABELS = {
            'catalog': _('Catalog'),
            'genres': _('Genres'),
            'franchises': _('Franchises'),
            'tags': _('Favorites & Tags'),
        }

        for tab_id in tab_ids:
            tab = get_tab(tab_id)
            if not tab:
                continue
            row = Adw.ActionRow(
                title=_TAB_LABELS.get(tab_id, tab['label']),
                icon_name=tab['icon'],
            )
            self.sidebar_list.append(row)

        self.sidebar_list.select_row(self.sidebar_list.get_row_at_index(0))

    def _build_bottom_bar(self):
        """Populate narrow bottom bar tabs and sheet from GSettings."""
        # Clear existing tab buttons
        child = self.narrow_tabs_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.narrow_tabs_box.remove(child)
            child = next_child

        # Clear sheet box
        child = self.narrow_sheet_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.narrow_sheet_box.remove(child)
            child = next_child

        tab_ids = get_visible_tabs(self._settings, is_narrow=True)
        self._narrow_tab_ids = tab_ids
        self._narrow_tab_buttons = {}

        _TAB_LABELS = {
            'catalog': _('Catalog'),
            'genres': _('Genres'),
            'franchises': _('Franchises'),
            'tags': _('Favorites'),
        }

        # Bottom bar: first 3 tabs as buttons
        for tab_id in tab_ids[:3]:
            tab = get_tab(tab_id)
            if not tab:
                continue
            btn = Gtk.Button()
            btn.add_css_class('flat')
            btn.add_css_class('nav-tab')
            box = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=2, halign=Gtk.Align.CENTER,
            )
            box.append(Gtk.Image(icon_name=tab['icon']))
            label = Gtk.Label(label=_TAB_LABELS.get(tab_id, tab['label']))
            label.add_css_class('caption')
            box.append(label)
            btn.set_child(box)
            btn.connect('clicked', self._on_narrow_tab_clicked, tab_id)
            self.narrow_tabs_box.append(btn)
            self._narrow_tab_buttons[tab_id] = btn

        # Always show drag handle (sheet has Preferences + About)
        self.narrow_drag_handle.set_visible(True)

        # Drag handle pill at top of sheet content
        sheet_handle = Gtk.Box(halign=Gtk.Align.CENTER,
                               margin_top=8, margin_bottom=4)
        pill = Gtk.Box(width_request=32, height_request=4,
                       valign=Gtk.Align.CENTER)
        pill.add_css_class('drag-handle-pill')
        sheet_handle.append(pill)
        gesture = Gtk.GestureClick.new()
        gesture.connect(
            'released',
            lambda *_: self.narrow_sheet.set_open(False),
        )
        sheet_handle.add_controller(gesture)
        self.narrow_sheet_box.append(sheet_handle)

        # Sheet content: grid or list style
        sheet_style = self._settings.get_string('navbar-sheet-style')
        if sheet_style == 'grid':
            self._build_sheet_grid(tab_ids, _TAB_LABELS)
        else:
            self._build_sheet_list(tab_ids, _TAB_LABELS)

        # Click on drag handle opens the sheet
        if self._drag_handle_gesture:
            self.narrow_drag_handle.remove_controller(
                self._drag_handle_gesture)
        self._drag_handle_gesture = Gtk.GestureClick.new()
        self._drag_handle_gesture.connect(
            'released',
            lambda *_: self.narrow_sheet.set_open(True),
        )
        self.narrow_drag_handle.add_controller(
            self._drag_handle_gesture)

    def _build_sheet_list(self, tab_ids, labels):
        """Build sheet content as a list of rows."""
        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        listbox.add_css_class('navigation-sidebar')
        for tab_id in tab_ids:
            tab = get_tab(tab_id)
            if not tab:
                continue
            row = Adw.ActionRow(
                title=labels.get(tab_id, tab['label']),
                icon_name=tab['icon'],
                activatable=True,
            )
            row._tab_id = tab_id
            listbox.append(row)
        listbox.connect('row-activated', self._on_sheet_row_activated)
        self.narrow_sheet_box.append(listbox)

        # Separator + app menu items
        self.narrow_sheet_box.append(Gtk.Separator(
            margin_top=4, margin_bottom=4))
        menu_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        menu_list.add_css_class('navigation-sidebar')
        prefs_row = Adw.ActionRow(
            title=_('Preferences'),
            icon_name='preferences-system-symbolic',
            activatable=True,
        )
        prefs_row._action = 'preferences'
        menu_list.append(prefs_row)
        about_row = Adw.ActionRow(
            title=_('About Kitsune'),
            icon_name='help-about-symbolic',
            activatable=True,
        )
        about_row._action = 'about'
        menu_list.append(about_row)
        menu_list.connect('row-activated', self._on_sheet_menu_activated)
        self.narrow_sheet_box.append(menu_list)

    def _build_sheet_grid(self, tab_ids, labels):
        """Build sheet content as a grid of icon buttons."""
        flow = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            homogeneous=True,
            max_children_per_line=4,
            min_children_per_line=3,
            row_spacing=8,
            column_spacing=8,
            margin_top=12,
            margin_bottom=12,
            margin_start=12,
            margin_end=12,
        )
        flow.add_css_class('sheet-grid')
        for tab_id in tab_ids:
            tab = get_tab(tab_id)
            if not tab:
                continue
            btn = Gtk.Button()
            btn.add_css_class('flat')
            btn.add_css_class('sheet-grid-item')
            box = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=4, halign=Gtk.Align.CENTER,
                valign=Gtk.Align.CENTER,
            )
            box.append(Gtk.Image(icon_name=tab['icon']))
            lbl = Gtk.Label(label=labels.get(tab_id, tab['label']))
            lbl.add_css_class('caption')
            box.append(lbl)
            btn.set_child(box)
            btn.connect('clicked', self._on_sheet_grid_clicked, tab_id)
            flow.append(btn)
        self.narrow_sheet_box.append(flow)

        # Separator + app menu items
        self.narrow_sheet_box.append(Gtk.Separator(
            margin_start=12, margin_end=12))
        menu_flow = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            homogeneous=True,
            max_children_per_line=4,
            min_children_per_line=3,
            row_spacing=8,
            column_spacing=8,
            margin_top=12,
            margin_bottom=12,
            margin_start=12,
            margin_end=12,
        )
        menu_flow.add_css_class('sheet-grid')
        for icon, label, action in (
            ('preferences-system-symbolic', _('Preferences'), 'preferences'),
            ('help-about-symbolic', _('About Kitsune'), 'about'),
        ):
            btn = Gtk.Button()
            btn.add_css_class('flat')
            btn.add_css_class('sheet-grid-item')
            box = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=4, halign=Gtk.Align.CENTER,
                valign=Gtk.Align.CENTER,
            )
            box.append(Gtk.Image(icon_name=icon))
            lbl = Gtk.Label(label=label)
            lbl.add_css_class('caption')
            box.append(lbl)
            btn.set_child(box)
            btn.connect('clicked', self._on_sheet_menu_clicked, action)
            menu_flow.append(btn)
        self.narrow_sheet_box.append(menu_flow)

    def _on_narrow_tab_clicked(self, _button, tab_id):
        self._switch_tab(tab_id)

    def _on_sheet_row_activated(self, _listbox, row):
        self.narrow_sheet.set_open(False)
        self._switch_tab(row._tab_id)

    def _on_sheet_grid_clicked(self, _button, tab_id):
        self.narrow_sheet.set_open(False)
        self._switch_tab(tab_id)

    def _on_sheet_menu_activated(self, _listbox, row):
        self.narrow_sheet.set_open(False)
        self._activate_menu_action(row._action)

    def _on_sheet_menu_clicked(self, _button, action):
        self.narrow_sheet.set_open(False)
        self._activate_menu_action(action)

    def _activate_menu_action(self, action):
        if action == 'preferences':
            self._on_preferences(None, None)
        elif action == 'about':
            self.get_application().activate_action('about', None)

    def _on_navbar_settings_changed(self, _settings, _key):
        """Rebuild navigation when settings change."""
        self._build_sidebar()
        self._build_bottom_bar()
        tab_ids = get_visible_tabs(self._settings, is_narrow=self._narrow)
        if tab_ids:
            self._switch_tab(tab_ids[0])

    def _create_genres_view(self):
        if self._genres_view:
            return
        from kitsune.ui.genres_view import GenresView
        old = self.content_stack.get_child_by_name('genres')
        if old:
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
        if old:
            self.content_stack.remove(old)
        self._franchises_view = FranchisesView(client=self._client)
        self._franchises_view.set_on_release_activated(self._show_release_detail)
        self._franchises_view.set_on_navigation_changed(self._on_sub_navigation_changed)
        self._franchises_view.set_narrow(self._narrow)
        self.content_stack.add_named(self._franchises_view, 'franchises')

    def _create_tags_view(self):
        if self._tags_view:
            return
        from kitsune.ui.tags_view import TagsView
        old = self.content_stack.get_child_by_name('tags')
        if old:
            self.content_stack.remove(old)
        saved_mode = self._settings.get_string('tags-view-mode')
        self._tags_view = TagsView(client=self._client)
        self._tags_view.set_on_release_activated(self._show_release_detail)
        self._tags_view.set_on_navigation_changed(self._on_sub_navigation_changed)
        self._tags_view.set_on_tags_changed(self._on_tags_bulk_changed)
        self._tags_view.set_narrow(self._narrow)
        self._tags_mode_is_list = saved_mode == 'list'
        if self._tags_mode_is_list:
            self._tags_view.toggle_mode()
            self.mode_btn.set_icon_name('view-grid-symbolic')
            self.mode_btn.set_tooltip_text(_('Card view'))
        self.content_stack.add_named(self._tags_view, 'tags')

    # --- Template Callbacks ---

    @Gtk.Template.Callback()
    def on_filter_clicked(self, _button):
        if not self.filter_split.get_sidebar():
            panel = self._catalog_view.get_or_create_filter_panel()
            panel.set_on_close(
                lambda: self.filter_split.set_show_sidebar(False)
            )
            self.filter_split.set_sidebar(panel)
        self.filter_split.set_show_sidebar(
            not self.filter_split.get_show_sidebar()
        )

    @Gtk.Template.Callback()
    def on_search_clicked(self, _button):
        self._open_search_dialog()

    @Gtk.Template.Callback()
    def on_back_clicked(self, _button):
        tab = self.content_stack.get_visible_child_name()
        if tab == 'genres' and self._genres_view:
            self._genres_view.go_back()
        elif tab == 'franchises' and self._franchises_view:
            self._franchises_view.go_back()
        elif tab == 'tags' and self._tags_view:
            self._tags_view.go_back()
        self._update_content_header()

    @Gtk.Template.Callback()
    def on_sidebar_row_selected(self, listbox, row):
        if not row:
            return
        index = row.get_index()
        if 0 <= index < len(self._sidebar_tab_ids):
            self._switch_tab(self._sidebar_tab_ids[index])

    @Gtk.Template.Callback()
    def on_mode_toggled(self, btn):
        if self._tags_view:
            self._tags_view.toggle_mode()
            self._tags_mode_is_list = not self._tags_mode_is_list
            mode = 'list' if self._tags_mode_is_list else 'cards'
            self._settings.set_string('tags-view-mode', mode)
            if self._tags_mode_is_list:
                btn.set_icon_name('view-grid-symbolic')
                btn.set_tooltip_text(_('Card view'))
            else:
                btn.set_icon_name('view-list-symbolic')
                btn.set_tooltip_text(_('List view'))

    @Gtk.Template.Callback()
    def on_add_tag_clicked(self, _button):
        from kitsune.ui.create_tag_dialog import show_create_tag_dialog
        show_create_tag_dialog(
            self,
            callback=self._on_header_tag_created,
        )

    def _on_header_tag_created(self, tag):
        if tag and self._tags_view:
            self._tags_view.refresh()

    @Gtk.Template.Callback()
    def on_delete_tag_clicked(self, _button):
        if self._tags_view and self._tags_view.current_tag:
            self._tags_view.delete_current_tag()

    @Gtk.Template.Callback()
    def on_narrow_apply(self, _bp):
        self._narrow = True
        self._catalog_view.set_narrow(True)
        if self._genres_view:
            self._genres_view.set_narrow(True)
        if self._franchises_view:
            self._franchises_view.set_narrow(True)
        if self._tags_view:
            self._tags_view.set_narrow(True)

    @Gtk.Template.Callback()
    def on_narrow_unapply(self, _bp):
        self._narrow = False
        self._catalog_view.set_narrow(False)
        if self._genres_view:
            self._genres_view.set_narrow(False)
        if self._franchises_view:
            self._franchises_view.set_narrow(False)
        if self._tags_view:
            self._tags_view.set_narrow(False)

    # --- Internal Methods ---

    def _switch_tab(self, name: str):
        self.filter_split.set_show_sidebar(False)
        if self._genres_view and self._genres_view.in_releases:
            self._genres_view.go_back()
        if self._franchises_view and self._franchises_view.in_releases:
            self._franchises_view.go_back()
        if self._tags_view and self._tags_view.in_releases:
            self._tags_view.go_back()
        if name == 'genres':
            self._create_genres_view()
        elif name == 'franchises':
            self._create_franchises_view()
        elif name == 'tags':
            self._create_tags_view()
            if self._tags_view:
                self._tags_view.refresh()
        self.content_stack.set_visible_child_name(name)
        self._update_content_header()
        self._update_nav_tabs(name)

    def _update_nav_tabs(self, active: str):
        for tab_id, btn in self._narrow_tab_buttons.items():
            if tab_id == active:
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
            'tags': _('Favorites & Tags'),
        }
        title = titles.get(tab, '')

        if tab == 'genres' and self._genres_view and self._genres_view.in_releases:
            title = self._genres_view.current_genre_name
            show_back = True
        elif tab == 'franchises' and self._franchises_view and self._franchises_view.in_releases:
            title = self._franchises_view.current_franchise_name
            show_back = True
        elif tab == 'tags' and self._tags_view and self._tags_view.in_releases:
            title = self._tags_view.current_tag_name
            show_back = True

        show_filter = (tab == 'catalog')
        show_tags_controls = (tab == 'tags' and not show_back)
        show_delete_tag = (
            tab == 'tags' and show_back
            and self._tags_view and self._tags_view.current_tag
            and not self._tags_view.current_tag.get('builtin')
        )

        self.wide_content_title.set_title(title)
        self.back_btn.set_visible(show_back)
        self.narrow_back_btn.set_visible(show_back)
        self.filter_btn.set_visible(show_filter)
        self.mode_btn.set_visible(show_tags_controls)
        self.add_tag_btn.set_visible(show_tags_controls)
        self.delete_tag_btn.set_visible(show_delete_tag)

    def _on_sub_navigation_changed(self):
        self._update_content_header()

    def _on_preferences(self, _action, _param):
        from kitsune.ui.preferences_window import PreferencesWindow
        prefs = PreferencesWindow()
        prefs.present(self)

    def _go_home(self):
        self.nav_view.pop_to_tag('main')

    def _show_release_detail(self, release):
        from kitsune.ui.release_view import ReleaseView
        view = ReleaseView(release=release, client=self._client)
        view.set_on_episode_play(self._play_episode)
        view.set_on_genre_clicked(self._navigate_to_genre)
        view.set_on_tag_clicked(self._navigate_to_tag)
        view.set_on_tags_changed(self._on_release_tags_changed)
        view.set_on_home_clicked(self._go_home)
        at_main = self.nav_view.get_visible_page().get_tag() == 'main'
        view.home_btn.set_visible(not at_main)
        self.nav_view.push(view)

    def _on_release_tags_changed(self, release_id):
        """Called when tags change on a release detail page."""
        self._refresh_visible_cards(release_id)
        if self._tags_view:
            self._tags_view.refresh()

    def _on_tags_bulk_changed(self, release_ids):
        """Called when a tag is deleted, affecting multiple releases."""
        for rid in release_ids:
            self._refresh_visible_cards(rid)

    def _refresh_visible_cards(self, release_id):
        """Find and refresh tag badges on visible ReleaseCard widgets."""
        from kitsune.ui.widgets.release_card import ReleaseCard
        flowboxes = []
        if self._catalog_view:
            flowboxes.append(self._catalog_view.flowbox)
        # Genre/franchise release sub-views contain ReleaseCards
        for view in (self._genres_view, self._franchises_view):
            if view and view._releases_view and hasattr(view._releases_view, '_grid'):
                flowboxes.append(view._releases_view._grid.flowbox)
        # Tags release sub-view
        if self._tags_view and self._tags_view.in_releases:
            releases = self._tags_view._nav_stack.get_child_by_name('releases')
            if releases and hasattr(releases, '_grid'):
                flowboxes.append(releases._grid.flowbox)
        for flowbox in flowboxes:
            child = flowbox.get_first_child()
            while child:
                if isinstance(child, ReleaseCard) and child.release.id == release_id:
                    child.refresh_tag_badges()
                child = child.get_next_sibling()

    def _make_nav_header(self):
        header = Adw.HeaderBar()
        home_btn = Gtk.Button(
            icon_name='net.armatik.Kitsune.home-symbolic',
            tooltip_text=_('Home'),
        )
        home_btn.connect('clicked', lambda *_: self._go_home())
        header.pack_start(home_btn)
        return header

    def _navigate_to_genre(self, genre):
        from kitsune.ui.genre_releases_view import GenreReleasesView
        releases_view = GenreReleasesView(
            genre=genre, client=self._client,
        )
        releases_view.set_on_release_activated(self._show_release_detail)
        releases_view.set_narrow(self._narrow)
        page = Adw.NavigationPage(
            title=genre.name,
            child=Adw.ToolbarView(
                top_bar_style=Adw.ToolbarStyle.FLAT,
                content=releases_view,
            ),
        )
        page.get_child().add_top_bar(self._make_nav_header())
        self.nav_view.push(page)

    def _open_search_dialog(self):
        from kitsune.ui.search_dialog import SearchDialog
        if not hasattr(self, '_search_dialog') or self._search_dialog is None:
            self._search_dialog = SearchDialog(client=self._client)
            self._search_dialog.set_on_release_activated(self._show_release_detail)
            self._search_dialog.set_on_episode_play(self._play_episode)
            self._search_dialog.set_on_genre_activated(self._navigate_to_genre)
            self._search_dialog.set_on_franchise_activated(self._navigate_to_franchise)
            self._search_dialog.set_on_tag_activated(self._navigate_to_tag)
        self._search_dialog.present(self)
        self._search_dialog.search_entry.grab_focus()

    def _navigate_to_franchise(self, franchise):
        from kitsune.ui.franchise_releases_view import FranchiseReleasesView
        releases_view = FranchiseReleasesView(
            franchise=franchise, client=self._client,
        )
        releases_view.set_on_release_activated(self._show_release_detail)
        releases_view.set_narrow(self._narrow)
        page = Adw.NavigationPage(
            title=franchise.name,
            child=Adw.ToolbarView(
                top_bar_style=Adw.ToolbarStyle.FLAT,
                content=releases_view,
            ),
        )
        page.get_child().add_top_bar(self._make_nav_header())
        self.nav_view.push(page)

    def _navigate_to_tag(self, tag):
        from kitsune.ui.tag_releases_view import TagReleasesView
        releases_view = TagReleasesView(
            tag=tag, client=self._client,
        )
        releases_view.set_on_release_activated(self._show_release_detail)
        releases_view.set_narrow(self._narrow)
        page = Adw.NavigationPage(
            title=tag['name'],
            child=Adw.ToolbarView(
                top_bar_style=Adw.ToolbarStyle.FLAT,
                content=releases_view,
            ),
        )
        page.get_child().add_top_bar(self._make_nav_header())
        self.nav_view.push(page)

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
        elif tab == 'tags' and self._tags_view:
            self._tags_view.refresh()

    def _on_nav_popped(self, _nav_view, page):
        self._stop_active_player()
        # Reopen search dialog if it was closed by navigating to a result
        if (hasattr(self, '_search_dialog') and self._search_dialog
                and self._search_dialog._closed_by_navigation
                and self.nav_view.get_visible_page() == self.nav_view.get_navigation_stack().get_item(0)):
            self._search_dialog._closed_by_navigation = False
            self._search_dialog.present(self)
            self._search_dialog.search_entry.grab_focus()

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
