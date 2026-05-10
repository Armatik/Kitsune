install_data(
  join_paths('hicolor', 'scalable', 'apps', 'net.armatik.Kitsune.svg'),
  install_dir: join_paths(get_option('datadir'), 'icons', 'hicolor', 'scalable', 'apps'),
)

install_data(
  join_paths('hicolor', 'symbolic', 'apps', 'net.armatik.Kitsune-symbolic.svg'),
  install_dir: join_paths(get_option('datadir'), 'icons', 'hicolor', 'symbolic', 'apps'),
)

action_icons = [
  'funnel-symbolic',
  'genres-symbolic',
  'franchises-symbolic',
  'magnet-symbolic',
  'cross-large-symbolic',
  'seek-backward-10-symbolic',
  'seek-forward-10-symbolic',
  'image-missing-symbolic',
  'sidebar-collapse-right-symbolic',
  'plus-circle-symbolic',
  'home-symbolic',
  'angled-arrows-symbolic',
  'update-symbolic',
  'settings-symbolic',
]

foreach icon : action_icons
  install_data(
    join_paths('hicolor', 'scalable', 'actions', APPLICATION_ID + '.' + icon + '.svg'),
    install_dir: join_paths(get_option('datadir'), 'icons', 'hicolor', 'scalable', 'actions'),
  )
endforeach
