"""Tests for asbdavani race / horse parsers using fixture HTML."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.asbdavani.parsers.horse import parse_horse_history_html
from src.asbdavani.parsers.race import parse_race_html
from src.asbdavani.constants import format_race_time, parse_race_url


FIXTURES = Path(__file__).parent / "fixtures"


def _escaped(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("\\", "\\\\").replace('"', r"\"")


def _wrap_rsc(inner: str) -> str:
    return f'<html><body><script>self.__next_f.push([1,"{inner}"])</script></body></html>'


@pytest.fixture
def race_html() -> str:
    week = {
        "id": "weekabc",
        "name": "هفته 2 گنبدکاووس 1398",
        "date": "2019-04-19T00:00:00.000Z",
        "leagueId": "league1",
        "races": [
            {
                "id": "race1",
                "round": 1,
                "name": "Maiden",
                "media": [
                    {"type": "APARAT"},
                    {
                        "url": "https://aparat.com/v/abc123",
                        "type": "APARAT",
                        "title": "Race film",
                        "name": "مستر",
                    },
                    {
                        "url": "photofinish/sample.jpg",
                        "type": "PHOTO_FINISH",
                        "title": "1",
                    },
                ],
                "plan": {
                    "name": "ترکمن 1000",
                    "distance": 1000,
                    "blood": "TURKMEN",
                    "age": "FREE_UPPER_3YO",
                },
                "prize": {
                    "name": "CLASS",
                    "prizes": [
                        {"rank": 1, "prize": 6200000},
                        {"rank": 2, "prize": 3100000},
                    ],
                },
                "raceHorses": [
                    {
                        "id": "rh1",
                        "weight": 53.5,
                        "owner": "مالک تست",
                        "coach": {"id": "c1", "name": "مربی یک"},
                        "rider": {"id": "j1", "name": "چابک یک"},
                        "entranceRating": 12,
                        "number": 1,
                        "rank": 1,
                        "extra": {"depar": 3},
                        "carriedWeight": 53.5,
                        "dl": 0,
                        "time": 72424,
                        "isRun": True,
                        "horse": {
                            "id": "h1",
                            "name": "اسب تست",
                            "sex": "MALE",
                            "birthdate": "2016-03-20T02:30:00.000Z",
                        },
                    },
                    {
                        "id": "rh2",
                        "weight": 56,
                        "owner": "مالک دو",
                        "coach": {"id": "c2", "name": "مربی دو"},
                        "rider": None,
                        "entranceRating": 0,
                        "number": 2,
                        "rank": 0,
                        "extra": None,
                        "dl": 0,
                        "time": 0,
                        "isRun": False,
                        "horse": {
                            "id": "h2",
                            "name": "اسب خارج",
                            "sex": "FEMALE",
                            "birthdate": "2017-03-21T00:00:00.000Z",
                        },
                    },
                ],
            }
        ],
    }
    leagues = [
        {
            "id": "league1",
            "location": {"id": "1", "name": "گنبدکاووس"},
            "season": "SPRING",
        }
    ]
    inner = (
        r'$L18",null,{"_weekInfo\":'
        + _escaped(week)
        + r',"leagues\":'
        + _escaped(leagues)
        + r',"raceNumber\":1}'
    )
    return _wrap_rsc(inner)


@pytest.fixture
def horse_html() -> str:
    entries = [
        {
            "id": "rhhist1",
            "owner": "مالک",
            "number": 6,
            "rank": 9,
            "extra": {"depar": 6},
            "weight": 54,
            "entranceRating": 60,
            "dl": 27.25,
            "time": 129617,
            "isRun": True,
            "race": {
                "id": "raceX",
                "round": 6,
                "name": "کلاس5",
                "week": {
                    "id": "weekX",
                    "name": "هفته 16 گنبدکاووس 1403",
                    "date": "2025-01-01T00:00:00.000Z",
                },
                "plan": {"distance": 1700, "blood": "TURKMEN"},
            },
            "horse": {
                "id": "h1",
                "name": "گنجیم درخشان",
                "sex": "MALE",
                "birthdate": "2021-03-21T10:59:00.000Z",
                "father": {"name": "سنان جان"},
                "mother": {"name": "لاچین گز"},
            },
            "coach": {"name": "امید یزدانی"},
            "rider": {"name": "چابک تست"},
        }
    ]
    # Matches site shape: {"data":{"data":[...]}}
    blob = {"data": {"data": entries}}
    inner = r'd:["$","div",null,{"children":["$","$L24",null,{"data\":' + _escaped(blob["data"]) + "}]}]"
    return _wrap_rsc(inner)


def test_parse_race_url() -> None:
    week_id, rnd = parse_race_url(
        "https://asbdavani.app/racecards/weekabc?round=1"
    )
    assert week_id == "weekabc"
    assert rnd == 1


def test_format_race_time() -> None:
    assert format_race_time(72424) == "1:12.424"
    assert format_race_time(0) is None


def test_parse_race_html(race_html: str) -> None:
    url = "https://asbdavani.app/racecards/weekabc?round=1"
    race = parse_race_html(race_html, url)
    assert race.race == "Maiden"
    assert race.race_number == 1
    assert race.distance == 1000
    assert race.track == "گنبدکاووس"
    assert race.racecourse_code == "gonbad-kavous"
    assert race.province == "گنبدکاووس"
    assert race.surface == "ترکمن"
    assert race.prize is not None
    assert len(race.media) == 3
    assert race.media[0] == {"type": "APARAT"}  # historical placeholder, no URL
    assert race.media[1]["url"] == "https://aparat.com/v/abc123"
    assert race.media[2]["url"] == "https://cdn.asbdavani.app/photofinish/sample.jpg"
    assert race.media[2]["type"] == "PHOTO_FINISH"
    assert len(race.horses) == 2

    winner = race.horses[0]
    assert winner.name == "اسب تست"
    assert winner.number == 1
    assert winner.jockey == "چابک یک"
    assert winner.trainer == "مربی یک"
    assert winner.finish_position == 1
    assert winner.time == "1:12.424"
    assert winner.barrier == 3
    assert winner.horse_profile_url.endswith("/performance/horses/h1")

    scratched = race.horses[1]
    assert scratched.finish_position is None


def test_parse_horse_history_html(horse_html: str) -> None:
    url = "https://asbdavani.app/performance/horses/h1"
    history = parse_horse_history_html(horse_html, url)
    assert history.horse.name == "گنجیم درخشان"
    assert history.horse.sire == "سنان جان"
    assert len(history.history) == 1
    row = history.history[0]
    assert row.finish_position == 9
    assert row.margin == 27.25
    assert row.barrier == 6
    assert row.race_number == 6
    assert row.track == "گنبدکاووس"
