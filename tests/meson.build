test_files = [
  'test_models.py',
  'test_watch_positions.py',
  'test_tags_store.py',
  'test_navbar.py',
  'test_content_grid.py',
  'test_tags_view_widget.py',
  'test_catalog_view_widget.py',
  'test_genres_view_widget.py',
  'test_release_card_widget.py',
  'test_tag_card_widget.py',
  'test_release_view_widget.py',
  'test_player_view_widget.py',
]

foreach test_file : test_files
  test_name = test_file.replace('.py', '').replace('test_', '')
  test(test_name, py_installation,
    args: ['-m', 'pytest', meson.current_source_dir() / test_file, '-v'],
    env: ['PYTHONPATH=' + meson.project_source_root() / 'src'],
  )
endforeach
