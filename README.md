<p align="center">
  <img src="data/icons/hicolor/scalable/apps/net.armatik.Kitsune.svg" width="128" height="128" alt="Kitsune">
</p>

<h1 align="center">Kitsune</h1>

<p align="center">Libadwaita-клиент для просмотра аниме от <a href="https://anilibria.top">AniLiberty</a></p>

<p align="center">
  <a href="https://altlinux.space/alt-gnome/Kitsune/src/branch/main/LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg" alt="License"></a>
</p>

> Kitsune — неофициальный клиент. Весь контент предоставляется командой [AniLiberty](https://anilibria.top) через их публичный API.

## Возможности

- Каталог релизов с фильтрами по жанрам, годам, сезонам и типам
- Поиск по названию с мгновенными результатами
- Страница релиза с информацией, списком серий, командой озвучки и торрентами
- Встроенный видеоплеер с HLS-воспроизведением и управлением качеством
- Просмотр по жанрам и франшизам
- Теги и избранное для организации библиотеки
- Отслеживание прогресса просмотра серий
- Настраиваемая навигация — порядок и видимость вкладок
- Сохранение позиции просмотра
- Кэширование постеров и данных релизов для офлайн-доступа
- Адаптивный интерфейс для десктопа и мобильных устройств
- Поддержка русского и английского языков

## Скриншоты

<p align="center">
  <img src="data/screenshots/Kitsune-1.png" alt="Kitsune">
</p>

## Установка

### Установка из репозитория ALT

```sh
apt-get update
apt-get install kitsune-adw
```

### Установка из ALS

```sh
apt-repo add rpm https://altlinux.space/api/packages/armatik/alt/group/sisyphus.repo noarch classic
apt-get update
apt-get install kitsune
```

### Сборка из исходников

**Зависимости:**

- Python 3.12+
- GTK 4
- Libadwaita 1.x
- GStreamer 1.x (с плагинами gtk4paintablesink, hlsdemux)
- Libsoup 3
- Meson 1.0+
- Blueprint Compiler

**Сборка и установка:**

```bash
meson setup _build
meson compile -C _build
sudo meson install -C _build --no-rebuild
```

## Сообщество

- [Telegram-канал](https://t.me/kitsune_linux) — новости и обновления
- [Telegram-чат](https://t.me/kitsune_linux_chat) — обсуждение и поддержка
- [Баг-трекер](https://altlinux.space/alt-gnome/Kitsune/issues) — сообщить об ошибке

## Участие в разработке

Проект приветствует вклад в виде исправлений и улучшений.

### Перевод

Работа с переводами ведётся через Meson:

```bash
meson compile -C _build kitsune-pot          # Обновить шаблон переводов
meson compile -C _build kitsune-update-po    # Обновить файлы переводов
```

## AniLiberty

Kitsune работает на базе контента команды [AniLiberty](https://anilibria.top) — некоммерческого проекта по переводу и озвучке аниме.

- [Сайт](https://anilibria.top)
- [Telegram](https://t.me/anilibria)
- [VK](https://vk.com/anilibria)
- [API документация](https://anilibria.top/api/docs/v1)

## Лицензия

Kitsune распространяется по лицензии [GPL-3.0-or-later](LICENSE).

---

> При разработке проекта использовались средства ИИ.
