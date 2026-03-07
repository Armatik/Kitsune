configure_file(
  input: 'main.py',
  output: 'kitsune',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
)

install_subdir('kitsune', install_dir: pkgdatadir, exclude_directories: ['__pycache__'])
