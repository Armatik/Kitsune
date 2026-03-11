test_files = [
  'test_models.py',
  'test_watch_positions.py',
  'test_tags_store.py',
  'test_navbar.py',
]

foreach test_file : test_files
  test_name = test_file.replace('.py', '').replace('test_', '')
  test(test_name, py_installation,
    args: ['-m', 'pytest', meson.current_source_dir() / test_file, '-v'],
    env: ['PYTHONPATH=' + meson.project_source_root() / 'src'],
  )
endforeach
