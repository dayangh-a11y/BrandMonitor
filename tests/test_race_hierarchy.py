"""Tests for Race Week → Race Day → Heat → Result hierarchy."""

from __future__ import annotations

import sqlite3

from src.hierarchy.keys import derive_heat_key, derive_race_day_id, derive_week_id
from src.hierarchy.rebuild import rebuild_hierarchy


def test_week_id_from_url_only():
    assert (
        derive_week_id("https://asbdavani.app/racecards/weekABC?round=3") == "weekABC"
    )
    assert derive_week_id(None) is None
    assert derive_week_id("https://asbdavani.app/horses/x") is None


def test_race_day_id_requires_date_and_venue():
    assert derive_race_day_id(race_date=None, racecourse_code="gonbad", week_id="w1") is None
    assert (
        derive_race_day_id(race_date="2026-08-01", racecourse_code="gonbad", week_id="w1")
        == "2026-08-01|gonbad|w1"
    )
    # No invented week — date+venue still forms a day id
    assert (
        derive_race_day_id(race_date="2026-08-01", racecourse_code="gonbad", week_id=None)
        == "2026-08-01|gonbad"
    )


def test_heat_key_never_bare_week_id():
    # Bare week_id as source_race_id is NOT a valid unique heat key
    assert (
        derive_heat_key(source_race_id="weekABC", week_id="weekABC", race_number=None)
        is None
    )
    assert (
        derive_heat_key(source_race_id="weekABC", week_id="weekABC", race_number=2)
        == "weekABC|round=2"
    )
    assert (
        derive_heat_key(source_race_id="heatXYZ", week_id="weekABC", race_number=1)
        == "heatXYZ"
    )


def _seed_mini_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE wh_horses (
            id INTEGER PRIMARY KEY,
            source TEXT, source_horse_id TEXT, name TEXT
        );
        CREATE TABLE wh_races (
            id INTEGER PRIMARY KEY,
            source TEXT,
            source_race_id TEXT,
            race_date TEXT,
            race_date_jalali TEXT,
            track TEXT,
            racecourse_code TEXT,
            province TEXT,
            race_number INTEGER,
            source_url TEXT
        );
        CREATE TABLE wh_race_results (
            id INTEGER PRIMARY KEY,
            race_id INTEGER,
            horse_id INTEGER,
            number INTEGER
        );
        """
    )
    # One Race Week, one Race Day, three Heats, five Results, four Horses
    week = "weekMini01"
    day = "2026-08-01"
    url = f"https://asbdavani.app/racecards/{week}?round={{}}"
    horses = [(1, "h1", "A"), (2, "h2", "B"), (3, "h3", "C"), (4, "h4", "D")]
    for hid, sid, name in horses:
        conn.execute(
            "INSERT INTO wh_horses (id, source, source_horse_id, name) VALUES (?,?,?,?)",
            (hid, "asbdavani", sid, name),
        )
    heats = [
        (10, "heatA", 1),
        (11, "heatB", 2),
        (12, "heatC", 3),
    ]
    for hid, sid, rnd in heats:
        conn.execute(
            """
            INSERT INTO wh_races (
                id, source, source_race_id, race_date, race_date_jalali,
                track, racecourse_code, province, race_number, source_url
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                hid,
                "asbdavani",
                sid,
                day,
                "1405/05/10",
                "گنبدکاووس",
                "gonbad",
                "گلستان",
                rnd,
                url.format(rnd),
            ),
        )
    # results: heat10 → horses 1,2 ; heat11 → 2,3 ; heat12 → 4
    results = [
        (1, 10, 1, 1),
        (2, 10, 2, 2),
        (3, 11, 2, 1),
        (4, 11, 3, 2),
        (5, 12, 4, 1),
    ]
    for rid, race_id, horse_id, number in results:
        conn.execute(
            "INSERT INTO wh_race_results (id, race_id, horse_id, number) VALUES (?,?,?,?)",
            (rid, race_id, horse_id, number),
        )
    conn.commit()


def test_rebuild_separates_heat_from_race_day():
    conn = sqlite3.connect(":memory:")
    _seed_mini_db(conn)
    stats = rebuild_hierarchy(conn)
    overall = stats["overall"]
    assert overall["race_weeks"] == 1
    assert overall["race_days"] == 1
    assert overall["heats"] == 3
    assert overall["results"] == 5
    assert overall["horses"] == 4
    assert overall["heats"] != overall["race_days"]

    day = stats["race_days"][0]
    assert day["heat_count"] == 3
    assert day["result_count"] == 5
    assert day["unique_horse_count"] == 4
    assert day["race_week_id"] == "weekMini01"
    assert day["race_date"] == "2026-08-01"
    assert day["city"] == "گنبدکاووس"

    # Hierarchy columns stamped on heats
    rows = conn.execute(
        "SELECT week_id, race_day_id, heat_key FROM wh_races ORDER BY id"
    ).fetchall()
    assert all(r[0] == "weekMini01" for r in rows)
    assert all(r[1] == "2026-08-01|gonbad|weekMini01" for r in rows)
    assert {r[2] for r in rows} == {"heatA", "heatB", "heatC"}
