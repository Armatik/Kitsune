# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SkipTimecode:
    start: float
    stop: float

    @classmethod
    def from_dict(cls, data: dict | None) -> SkipTimecode | None:
        if not data:
            return None
        return cls(start=data.get('start', 0), stop=data.get('stop', 0))


def _genre_image_url(data: dict | None) -> str | None:
    if not data:
        return None
    optimized = data.get('optimized')
    if optimized and optimized.get('preview'):
        return 'https://anilibria.top' + optimized['preview']
    preview = data.get('preview')
    if preview:
        return 'https://anilibria.top' + preview
    return None


@dataclass
class Genre:
    id: int
    name: str
    image: str | None = None
    total_releases: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> Genre:
        return cls(
            id=data['id'],
            name=data['name'],
            image=_genre_image_url(data.get('image')),
            total_releases=data.get('total_releases', 0),
        )


@dataclass
class ReleaseName:
    main: str
    english: str | None = None
    alternative: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> ReleaseName:
        return cls(
            main=data.get('main', ''),
            english=data.get('english'),
            alternative=data.get('alternative'),
        )


def _poster_url(data: dict | None) -> str | None:
    if not data:
        return None
    optimized = data.get('optimized')
    if optimized and optimized.get('src'):
        return 'https://anilibria.top' + optimized['src']
    src = data.get('src')
    if src:
        return 'https://anilibria.top' + src
    return None


@dataclass
class Episode:
    id: str
    name: str | None
    ordinal: float
    hls_480: str | None = None
    hls_720: str | None = None
    hls_1080: str | None = None
    duration: int | None = None
    opening: SkipTimecode | None = None
    ending: SkipTimecode | None = None
    preview: str | None = None
    sort_order: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> Episode:
        return cls(
            id=data['id'],
            name=data.get('name'),
            ordinal=data.get('ordinal', 0),
            hls_480=data.get('hls_480'),
            hls_720=data.get('hls_720'),
            hls_1080=data.get('hls_1080'),
            duration=data.get('duration'),
            opening=SkipTimecode.from_dict(data.get('opening')),
            ending=SkipTimecode.from_dict(data.get('ending')),
            preview=_poster_url(data.get('preview')),
            sort_order=data.get('sort_order', 0),
        )

    def get_hls_url(self, quality: str = '1080') -> str | None:
        urls = {'1080': self.hls_1080, '720': self.hls_720, '480': self.hls_480}
        url = urls.get(quality)
        if url:
            return url
        for q in ('1080', '720', '480'):
            if urls.get(q):
                return urls[q]
        return None


@dataclass
class Release:
    id: int
    name: ReleaseName
    alias: str
    description: str | None = None
    poster: str | None = None
    type: str = ''
    year: int = 0
    season: str | None = None
    age_rating: str = ''
    episodes_total: int | None = None
    is_ongoing: bool = False
    genres: list[Genre] = field(default_factory=list)
    episodes: list[Episode] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> Release:
        name_data = data.get('name', {})
        type_data = data.get('type', {})
        season_data = data.get('season')
        age_data = data.get('age_rating', {})

        genres = [Genre.from_dict(g) for g in data.get('genres', [])]
        episodes = [Episode.from_dict(e) for e in data.get('episodes', [])]
        episodes.sort(key=lambda e: e.sort_order)

        return cls(
            id=data['id'],
            name=ReleaseName.from_dict(name_data) if isinstance(name_data, dict) else ReleaseName(main=str(name_data)),
            alias=data.get('alias', ''),
            description=data.get('description'),
            poster=_poster_url(data.get('poster')),
            type=type_data.get('value', '') if isinstance(type_data, dict) else str(type_data),
            year=data.get('year', 0),
            season=season_data.get('value') if isinstance(season_data, dict) else season_data,
            age_rating=age_data.get('value', '') if isinstance(age_data, dict) else str(age_data),
            episodes_total=data.get('episodes_total'),
            is_ongoing=data.get('is_ongoing', False),
            genres=genres,
            episodes=episodes,
        )
