# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from dataclasses import dataclass, field

from kitsune.models.release import Release


def _franchise_image_url(data: dict | None) -> str | None:
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
class Franchise:
    id: str
    name: str
    name_english: str | None = None
    image: str | None = None
    first_year: int | None = None
    last_year: int | None = None
    total_releases: int | None = None
    total_episodes: int | None = None
    releases: list[Release] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> Franchise:
        releases = []
        for fr in data.get('franchise_releases', []):
            rel_data = fr.get('release')
            if rel_data:
                releases.append(Release.from_dict(rel_data))

        return cls(
            id=data['id'],
            name=data.get('name', ''),
            name_english=data.get('name_english'),
            image=_franchise_image_url(data.get('image')),
            first_year=data.get('first_year'),
            last_year=data.get('last_year'),
            total_releases=data.get('total_releases'),
            total_episodes=data.get('total_episodes'),
            releases=releases,
        )
