# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

_css_loaded = False


def _ensure_css():
    global _css_loaded
    if _css_loaded:
        return
    _css_loaded = True
    css = Gtk.CssProvider()
    css.load_from_string(
        '.filter-chip { padding: 4px 10px; min-height: 0; min-width: 0; font-size: 13px; }'
        ' .filter-chip:checked { background: @accent_bg_color; color: @accent_fg_color; }'
    )
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), css,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


def _types():
    return [
        ('TV', _('TV')),
        ('ONA', 'ONA'),
        ('WEB', 'WEB'),
        ('OVA', 'OVA'),
        ('OAD', 'OAD'),
        ('MOVIE', _('Movie')),
        ('DORAMA', _('Dorama')),
        ('SPECIAL', _('Special')),
    ]


def _seasons():
    return [
        ('winter', _('Winter')),
        ('spring', _('Spring')),
        ('summer', _('Summer')),
        ('autumn', _('Autumn')),
    ]


def _age_ratings():
    return [
        ('R0_PLUS', '0+'),
        ('R6_PLUS', '6+'),
        ('R12_PLUS', '12+'),
        ('R16_PLUS', '16+'),
        ('R18_PLUS', '18+'),
    ]


def _sorting():
    return [
        (None, _('By default')),
        ('FRESH_AT_DESC', _('Recently updated')),
        ('YEAR_DESC', _('Year (new ones first)')),
        ('YEAR_ASC', _('Year (old ones first)')),
        ('RATING_DESC', _('By rating')),
    ]


def _publish_statuses():
    return [
        ('IS_ONGOING', _('Ongoing')),
        ('IS_NOT_ONGOING', _('Not ongoing')),
    ]


def _production_statuses():
    return [
        ('IS_IN_PRODUCTION', _('Now dubbing')),
        ('IS_NOT_IN_PRODUCTION', _('Dubbing completed')),
    ]


class FilterDialog(Adw.Dialog):

    def __init__(self, genres: list | None = None,
                 year_range: tuple[int, int] | None = None, **kwargs):
        super().__init__(title=_('Filters'), **kwargs)
        _ensure_css()
        self.set_can_close(True)
        self.set_content_width(400)
        self.set_content_height(520)

        self._genres_data = genres or []
        self._year_min, self._year_max = year_range or (1990, 2026)
        self._on_apply = None
        self._buttons: dict[str, dict] = {}
        self._selected_sorting: str | None = None
        self._sorting_items = _sorting()

        self._build_ui()

    def set_on_apply(self, callback):
        self._on_apply = callback

    def set_filters(self, filters: dict):
        for cat, btns in self._buttons.items():
            selected = set(filters.get(cat, []))
            for val, btn in btns.items():
                btn.set_active(val in selected)

        years = filters.get('years', {})
        self._year_from.set_value(years.get('from_year', self._year_min))
        self._year_to.set_value(years.get('to_year', self._year_max))

        self._selected_sorting = filters.get('sorting')
        self._update_sorting_label()
        self._update_reset_sensitivity()

    def get_filters(self) -> dict:
        filters = {}
        for cat, btns in self._buttons.items():
            selected = [v for v, b in btns.items() if b.get_active()]
            if selected:
                filters[cat] = selected

        if self._selected_sorting:
            filters['sorting'] = self._selected_sorting

        year_from = int(self._year_from.get_value())
        year_to = int(self._year_to.get_value())
        if year_from != self._year_min or year_to != self._year_max:
            filters['years'] = {'from_year': year_from, 'to_year': year_to}
        return filters

    def _has_any_selection(self) -> bool:
        for btns in self._buttons.values():
            for btn in btns.values():
                if btn.get_active():
                    return True
        if self._selected_sorting is not None:
            return True
        if int(self._year_from.get_value()) != self._year_min:
            return True
        if int(self._year_to.get_value()) != self._year_max:
            return True
        return False

    def _update_reset_sensitivity(self):
        self._reset_btn.set_sensitive(self._has_any_selection())

    def _update_sorting_label(self):
        label = self._sorting_items[0][1]  # Default
        for val, lbl in self._sorting_items:
            if val == self._selected_sorting:
                label = lbl
                break
        self._sorting_btn.set_label(label)

    def _build_ui(self):
        toolbar = Adw.ToolbarView()

        # Header (title only, no buttons)
        header = Adw.HeaderBar(show_title=True)
        header.set_show_back_button(False)
        header.set_show_end_title_buttons(False)
        header.set_show_start_title_buttons(False)
        header.set_decoration_layout('')
        toolbar.add_top_bar(header)

        # Content
        scrolled = Gtk.ScrolledWindow(vexpand=True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
            margin_start=12,
            margin_end=12,
            margin_top=8,
            margin_bottom=12,
        )

        # Sorting — row: heading left, dropdown button right
        sorting_box = Gtk.Box(spacing=8, margin_top=2)
        sorting_label = Gtk.Label(
            label=_('Sorting'),
            xalign=0,
            css_classes=['heading'],
            hexpand=True,
        )
        sorting_box.append(sorting_label)

        sorting_menu = Gio.Menu()
        for val, lbl in self._sorting_items:
            item = Gio.MenuItem.new(lbl, None)
            item.set_action_and_target_value(
                'filter.set-sorting',
                GLib.Variant.new_string(val or ''),
            )
            sorting_menu.append_item(item)

        self._sorting_btn = Gtk.MenuButton(
            css_classes=['flat'],
            halign=Gtk.Align.END,
        )
        self._sorting_btn.set_menu_model(sorting_menu)

        action_group = Gio.SimpleActionGroup()
        sorting_action = Gio.SimpleAction.new('set-sorting', GLib.VariantType.new('s'))
        sorting_action.connect('activate', self._on_sorting_selected)
        action_group.add_action(sorting_action)
        self._sorting_btn.insert_action_group('filter', action_group)

        self._update_sorting_label()
        sorting_box.append(self._sorting_btn)
        content.append(sorting_box)

        # Year range — heading + two SpinButtons on one row
        year_label = Gtk.Label(
            label=_('Release period'),
            xalign=0,
            css_classes=['heading'],
            margin_top=2,
        )
        content.append(year_label)

        year_box = Gtk.Box(spacing=8)
        year_box.append(Gtk.Label(label=_('from')))

        self._year_from = Gtk.SpinButton.new_with_range(
            self._year_min, self._year_max, 1,
        )
        self._year_from.set_value(self._year_min)
        self._year_from.set_hexpand(True)
        self._year_from.connect('value-changed', self._on_year_changed)
        year_box.append(self._year_from)

        year_box.append(Gtk.Label(label=_('to')))

        self._year_to = Gtk.SpinButton.new_with_range(
            self._year_min, self._year_max, 1,
        )
        self._year_to.set_value(self._year_max)
        self._year_to.set_hexpand(True)
        self._year_to.connect('value-changed', self._on_year_changed)
        year_box.append(self._year_to)

        content.append(year_box)

        # Filter sections
        categories = [
            ('types', _('Type'), _types()),
            ('seasons', _('Season'), _seasons()),
            ('age_ratings', _('Age Rating'), _age_ratings()),
            ('publish_statuses', _('Release status'), _publish_statuses()),
            ('production_statuses', _('Dubbing status'), _production_statuses()),
        ]
        if self._genres_data:
            categories.append(
                ('genres', _('Genres'), [(g['id'], g['name']) for g in self._genres_data])
            )

        for cat, title, items in categories:
            if items:
                self._add_chip_section(content, cat, title, items)

        scrolled.set_child(content)
        toolbar.set_content(scrolled)

        # Bottom button bar
        button_bar = Gtk.Box(
            spacing=8,
            homogeneous=True,
            margin_start=12,
            margin_end=12,
            margin_top=8,
            margin_bottom=8,
        )

        cancel_btn = Gtk.Button(label=_('Cancel'))
        cancel_btn.connect('clicked', self._on_cancel)
        button_bar.append(cancel_btn)

        self._reset_btn = Gtk.Button(
            label=_('Reset'),
            css_classes=['destructive-action'],
            sensitive=False,
        )
        self._reset_btn.connect('clicked', self._on_reset)
        button_bar.append(self._reset_btn)

        apply_btn = Gtk.Button(
            label=_('Apply'),
            css_classes=['suggested-action'],
        )
        apply_btn.connect('clicked', self._on_apply_clicked)
        button_bar.append(apply_btn)

        toolbar.add_bottom_bar(button_bar)
        self.set_child(toolbar)

    def _add_chip_section(self, parent, cat: str, title: str, items: list):
        self._buttons[cat] = {}

        label = Gtk.Label(
            label=title,
            xalign=0,
            css_classes=['heading'],
            margin_top=2,
        )
        parent.append(label)

        wrap = Adw.WrapBox(line_spacing=6, child_spacing=6)
        for value, item_label in items:
            btn = Gtk.ToggleButton(
                label=item_label,
                css_classes=['pill', 'filter-chip'],
            )
            btn.connect('toggled', self._on_any_changed)
            wrap.append(btn)
            self._buttons[cat][value] = btn
        parent.append(wrap)

    def _on_sorting_selected(self, action, variant):
        val = variant.get_string()
        self._selected_sorting = val if val else None
        self._update_sorting_label()
        self._update_reset_sensitivity()

    def _on_year_changed(self, spin):
        year_from = int(self._year_from.get_value())
        year_to = int(self._year_to.get_value())
        if spin == self._year_from and year_from > year_to:
            self._year_to.set_value(year_from)
        elif spin == self._year_to and year_to < year_from:
            self._year_from.set_value(year_to)
        self._update_reset_sensitivity()

    def _on_any_changed(self, *args):
        self._update_reset_sensitivity()

    def _on_cancel(self, _button):
        self.force_close()

    def _on_reset(self, _button):
        for btns in self._buttons.values():
            for btn in btns.values():
                btn.set_active(False)
        self._selected_sorting = None
        self._update_sorting_label()
        self._year_from.set_value(self._year_min)
        self._year_to.set_value(self._year_max)

    def _on_apply_clicked(self, _button):
        if self._on_apply:
            self._on_apply(self.get_filters())
        self.force_close()
