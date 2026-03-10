configure_file(
  input: 'main.py',
  output: 'kitsune',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
)

blueprint_compiler = find_program('blueprint-compiler')

blueprints_ui = custom_target('blueprints-ui',
  input: files(
    'kitsune/ui/window.blp',
    'kitsune/ui/preferences_window.blp',
    'kitsune/ui/search_view.blp',
    'kitsune/ui/release_view.blp',
    'kitsune/ui/filter_dialog.blp',
    'kitsune/ui/player_view.blp',
  ),
  output: [
    'window.ui',
    'preferences_window.ui',
    'search_view.ui',
    'release_view.ui',
    'filter_dialog.ui',
    'player_view.ui',
  ],
  command: [blueprint_compiler, 'batch-compile', '@OUTDIR@', '@CURRENT_SOURCE_DIR@/kitsune/ui', '@INPUT@'],
)

blueprints_widgets = custom_target('blueprints-widgets',
  input: files(
    'kitsune/ui/widgets/content_grid.blp',
    'kitsune/ui/widgets/release_card.blp',
    'kitsune/ui/widgets/genre_card.blp',
    'kitsune/ui/widgets/franchise_card.blp',
    'kitsune/ui/widgets/tag_card.blp',
  ),
  output: [
    'content_grid.ui',
    'release_card.ui',
    'genre_card.ui',
    'franchise_card.ui',
    'tag_card.ui',
  ],
  command: [blueprint_compiler, 'batch-compile', '@OUTDIR@', '@CURRENT_SOURCE_DIR@/kitsune/ui/widgets', '@INPUT@'],
)

gnome.compile_resources(
  'net.armatik.Kitsune',
  'kitsune.gresource.xml',
  dependencies: [blueprints_ui, blueprints_widgets],
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
)

install_subdir('kitsune', install_dir: pkgdatadir,
  exclude_directories: ['__pycache__'],
  exclude_files: [
    'ui/window.blp',
    'ui/preferences_window.blp',
    'ui/search_view.blp',
    'ui/release_view.blp',
    'ui/filter_dialog.blp',
    'ui/player_view.blp',
    'ui/widgets/content_grid.blp',
    'ui/widgets/release_card.blp',
    'ui/widgets/genre_card.blp',
    'ui/widgets/franchise_card.blp',
    'ui/widgets/tag_card.blp',
  ],
)
