"""Tests for DataSource registry isolation."""

from __future__ import annotations

from src.datasources import DataSource, get_datasource, list_datasources
from src.models import HorseHistory, HorseProfile, Race, RaceListItem


class DummySource(DataSource):
    name = "dummy"

    def collect_race(self, url: str) -> Race:
        return Race(
            race="x",
            track="گنبدکاووس",
            racecourse_code="gonbad-kavous",
            sourceUrl=url,
            horses=[],
        )

    def collect_horse(self, url: str) -> HorseProfile:
        return HorseProfile(name="h", profileUrl=url)

    def collect_horse_history(self, url: str) -> HorseHistory:
        return HorseHistory(horse=HorseProfile(name="h", profileUrl=url), history=[])

    def collect_race_list(self, url: str | None = None) -> list[RaceListItem]:
        return []


def test_asbdavani_registered() -> None:
    names = list_datasources()
    assert "asbdavani" in names


def test_get_asbdavani_datasource() -> None:
    ds = get_datasource("asbdavani")
    assert ds.name == "asbdavani"
    ds.close()


def test_custom_register() -> None:
    from src.datasources.registry import register_datasource

    register_datasource("dummy", DummySource)
    assert "dummy" in list_datasources()
    ds = get_datasource("dummy")
    race = ds.collect_race("https://example.com/race")
    assert race.race == "x"
