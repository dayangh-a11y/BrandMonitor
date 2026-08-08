"""Rebuild Race Week → Race Day → Heat → Result hierarchy from warehouse rows."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import jdatetime

from src.hierarchy.keys import derive_heat_key, derive_race_day_id, derive_week_id
from src.utils.jalali import format_jalali

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS wh_race_weeks (
    race_week_id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'asbdavani',
    source_url TEXT,
    heat_count INTEGER NOT NULL DEFAULT 0,
    race_day_count INTEGER NOT NULL DEFAULT 0,
    result_count INTEGER NOT NULL DEFAULT 0,
    unique_horse_count INTEGER NOT NULL DEFAULT 0,
    first_race_date TEXT,
    last_race_date TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wh_race_days (
    race_day_id TEXT PRIMARY KEY,
    race_week_id TEXT,
    race_date TEXT NOT NULL,
    race_date_jalali TEXT,
    jalali_year INTEGER,
    track TEXT NOT NULL,
    racecourse_code TEXT NOT NULL,
    city TEXT,
    heat_count INTEGER NOT NULL DEFAULT 0,
    result_count INTEGER NOT NULL DEFAULT 0,
    unique_horse_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (race_week_id) REFERENCES wh_race_weeks(race_week_id)
);

CREATE INDEX IF NOT EXISTS ix_wh_race_days_date ON wh_race_days(race_date);
CREATE INDEX IF NOT EXISTS ix_wh_race_days_week ON wh_race_days(race_week_id);
CREATE INDEX IF NOT EXISTS ix_wh_race_days_jalali_year ON wh_race_days(jalali_year);

CREATE TABLE IF NOT EXISTS wh_heat_hierarchy (
    heat_id INTEGER PRIMARY KEY,
    heat_key TEXT,
    race_day_id TEXT,
    race_week_id TEXT,
    source_race_id TEXT,
    race_number INTEGER,
    race_date TEXT,
    track TEXT,
    racecourse_code TEXT,
    source_url TEXT,
    result_count INTEGER NOT NULL DEFAULT 0,
    unique_horse_count INTEGER NOT NULL DEFAULT 0,
    link_complete INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (race_day_id) REFERENCES wh_race_days(race_day_id),
    FOREIGN KEY (race_week_id) REFERENCES wh_race_weeks(race_week_id)
);

CREATE INDEX IF NOT EXISTS ix_wh_heat_hierarchy_day ON wh_heat_hierarchy(race_day_id);
CREATE INDEX IF NOT EXISTS ix_wh_heat_hierarchy_week ON wh_heat_hierarchy(race_week_id);
CREATE INDEX IF NOT EXISTS ix_wh_heat_hierarchy_key ON wh_heat_hierarchy(heat_key);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gdate(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    try:
        y, m, d = map(int, text.split("-"))
        return date(y, m, d)
    except ValueError:
        return None


def _ensure_columns(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(wh_races)").fetchall()}
    alters: list[str] = []
    if "week_id" not in cols:
        alters.append("ALTER TABLE wh_races ADD COLUMN week_id TEXT")
    if "race_day_id" not in cols:
        alters.append("ALTER TABLE wh_races ADD COLUMN race_day_id TEXT")
    if "heat_key" not in cols:
        alters.append("ALTER TABLE wh_races ADD COLUMN heat_key TEXT")
    for sql in alters:
        conn.execute(sql)
    conn.execute("CREATE INDEX IF NOT EXISTS ix_wh_races_week_id ON wh_races(week_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_wh_races_race_day_id ON wh_races(race_day_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_wh_races_heat_key ON wh_races(heat_key)")


def rebuild_hierarchy(conn: sqlite3.Connection) -> dict[str, Any]:
    """Materialize hierarchy tables from ``wh_races`` + ``wh_race_results``.

    A Heat is never counted as a Race Day.
    """
    conn.executescript(SCHEMA_SQL)
    _ensure_columns(conn)
    now = _now()

    heats = conn.execute(
        """
        SELECT id, source, source_race_id, race_date, race_date_jalali,
               track, racecourse_code, province, race_number, source_url
        FROM wh_races
        """
    ).fetchall()

    result_stats = {
        int(r[0]): (int(r[1]), int(r[2]))
        for r in conn.execute(
            """
            SELECT race_id,
                   COUNT(*) AS result_count,
                   COUNT(DISTINCT horse_id) AS unique_horses
            FROM wh_race_results
            GROUP BY race_id
            """
        )
    }
    horses_by_heat: dict[int, set[int]] = defaultdict(set)
    for race_id, horse_id in conn.execute(
        """
        SELECT race_id, horse_id FROM wh_race_results
        WHERE horse_id IS NOT NULL
        """
    ):
        horses_by_heat[int(race_id)].add(int(horse_id))

    week_rows: dict[str, dict[str, Any]] = {}
    day_rows: dict[str, dict[str, Any]] = {}
    heat_rows: list[dict[str, Any]] = []
    incomplete = {
        "heats_missing_week": 0,
        "heats_missing_race_day": 0,
        "heats_missing_heat_key": 0,
    }

    for row in heats:
        (
            heat_id,
            source,
            source_race_id,
            race_date,
            race_date_jalali,
            track,
            racecourse_code,
            province,
            race_number,
            source_url,
        ) = row
        week_id = derive_week_id(source_url)
        on = _gdate(race_date)
        race_day_id = derive_race_day_id(
            race_date=on,
            racecourse_code=racecourse_code,
            week_id=week_id,
            track=track,
        )
        heat_key = derive_heat_key(
            source_race_id=source_race_id,
            week_id=week_id,
            race_number=race_number,
            source_url=source_url,
        )
        rc, uh = result_stats.get(int(heat_id), (0, 0))
        link_complete = bool(week_id and race_day_id and heat_key)

        if not week_id:
            incomplete["heats_missing_week"] += 1
        if not race_day_id:
            incomplete["heats_missing_race_day"] += 1
        if not heat_key:
            incomplete["heats_missing_heat_key"] += 1

        conn.execute(
            """
            UPDATE wh_races
            SET week_id = ?, race_day_id = ?, heat_key = ?
            WHERE id = ?
            """,
            (week_id, race_day_id, heat_key, heat_id),
        )

        horse_ids = horses_by_heat.get(int(heat_id), set())

        if week_id:
            w = week_rows.setdefault(
                week_id,
                {
                    "race_week_id": week_id,
                    "source": source or "asbdavani",
                    "source_url": f"https://asbdavani.app/racecards/{week_id}",
                    "heat_count": 0,
                    "result_count": 0,
                    "horses": set(),
                    "days": set(),
                    "dates": [],
                },
            )
            w["heat_count"] += 1
            w["result_count"] += rc
            w["horses"].update(horse_ids)
            if race_day_id:
                w["days"].add(race_day_id)
            if on:
                w["dates"].append(on)

        if race_day_id and on:
            jalali = race_date_jalali or format_jalali(on)
            jy = None
            if jalali:
                try:
                    jy = int(str(jalali).replace("-", "/").split("/")[0])
                except ValueError:
                    jy = None
            if jy is None:
                jy = jdatetime.date.fromgregorian(date=on).year
            d = day_rows.setdefault(
                race_day_id,
                {
                    "race_day_id": race_day_id,
                    "race_week_id": week_id,
                    "race_date": on.isoformat(),
                    "race_date_jalali": jalali,
                    "jalali_year": jy,
                    "track": track,
                    "racecourse_code": racecourse_code,
                    "city": track or province,
                    "heat_count": 0,
                    "result_count": 0,
                    "horses": set(),
                },
            )
            d["heat_count"] += 1
            d["result_count"] += rc
            d["horses"].update(horse_ids)
            if week_id and not d.get("race_week_id"):
                d["race_week_id"] = week_id

        heat_rows.append(
            {
                "heat_id": int(heat_id),
                "heat_key": heat_key,
                "race_day_id": race_day_id,
                "race_week_id": week_id,
                "source_race_id": source_race_id,
                "race_number": race_number,
                "race_date": on.isoformat() if on else None,
                "track": track,
                "racecourse_code": racecourse_code,
                "source_url": source_url,
                "result_count": rc,
                "unique_horse_count": uh,
                "link_complete": 1 if link_complete else 0,
                "updated_at": now,
            }
        )

    conn.execute("DELETE FROM wh_heat_hierarchy")
    conn.execute("DELETE FROM wh_race_days")
    conn.execute("DELETE FROM wh_race_weeks")

    for wid, w in week_rows.items():
        dates = sorted(w["dates"])
        conn.execute(
            """
            INSERT INTO wh_race_weeks (
                race_week_id, source, source_url, heat_count, race_day_count,
                result_count, unique_horse_count, first_race_date, last_race_date,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                wid,
                w["source"],
                w["source_url"],
                w["heat_count"],
                len({x for x in w["days"] if x}),
                w["result_count"],
                len(w["horses"]),
                dates[0].isoformat() if dates else None,
                dates[-1].isoformat() if dates else None,
                now,
            ),
        )

    for did, d in day_rows.items():
        conn.execute(
            """
            INSERT INTO wh_race_days (
                race_day_id, race_week_id, race_date, race_date_jalali, jalali_year,
                track, racecourse_code, city, heat_count, result_count,
                unique_horse_count, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                did,
                d.get("race_week_id"),
                d["race_date"],
                d.get("race_date_jalali"),
                d.get("jalali_year"),
                d["track"],
                d["racecourse_code"],
                d.get("city"),
                d["heat_count"],
                d["result_count"],
                len(d["horses"]),
                now,
            ),
        )

    conn.executemany(
        """
        INSERT INTO wh_heat_hierarchy (
            heat_id, heat_key, race_day_id, race_week_id, source_race_id,
            race_number, race_date, track, racecourse_code, source_url,
            result_count, unique_horse_count, link_complete, updated_at
        ) VALUES (
            :heat_id, :heat_key, :race_day_id, :race_week_id, :source_race_id,
            :race_number, :race_date, :track, :racecourse_code, :source_url,
            :result_count, :unique_horse_count, :link_complete, :updated_at
        )
        """,
        heat_rows,
    )
    conn.commit()

    stats = recount_hierarchy(conn)
    stats["incomplete_links"] = incomplete
    stats["rebuilt_at"] = now
    return stats


def recount_hierarchy(conn: sqlite3.Connection) -> dict[str, Any]:
    """Recount hierarchy metrics. Heat ≠ Race Day."""

    def _count(sql: str) -> int:
        return int(conn.execute(sql).fetchone()[0])

    overall = {
        "race_weeks": _count("SELECT COUNT(*) FROM wh_race_weeks"),
        "race_days": _count("SELECT COUNT(*) FROM wh_race_days"),
        "heats": _count("SELECT COUNT(*) FROM wh_races"),
        "results": _count("SELECT COUNT(*) FROM wh_race_results"),
        "horses": _count("SELECT COUNT(*) FROM wh_horses"),
        # Sanity: never treat heat count as race day count
        "heats_equals_race_days": False,
    }
    overall["heats_equals_race_days"] = overall["heats"] == overall["race_days"] and overall["heats"] > 0

    by_year: list[dict[str, Any]] = []
    years = conn.execute(
        """
        SELECT jalali_year,
               COUNT(*) AS race_days,
               SUM(heat_count) AS heats,
               SUM(result_count) AS results,
               SUM(unique_horse_count) AS horse_starts_unique_per_day
        FROM wh_race_days
        WHERE jalali_year IS NOT NULL
        GROUP BY jalali_year
        ORDER BY jalali_year
        """
    ).fetchall()

    # Unique horses per Jalali year (global distinct within year, not sum of day uniques)
    for y, days, heats, results, _horses_sum in years:
        horses = conn.execute(
            """
            SELECT COUNT(DISTINCT rr.horse_id)
            FROM wh_race_results rr
            JOIN wh_heat_hierarchy h ON h.heat_id = rr.race_id
            JOIN wh_race_days d ON d.race_day_id = h.race_day_id
            WHERE rr.horse_id IS NOT NULL AND d.jalali_year = ?
            """,
            (int(y),),
        ).fetchone()[0]
        weeks = conn.execute(
            """
            SELECT COUNT(DISTINCT race_week_id)
            FROM wh_race_days
            WHERE jalali_year = ? AND race_week_id IS NOT NULL
            """,
            (int(y),),
        ).fetchone()[0]
        by_year.append(
            {
                "jalali_year": int(y),
                "race_weeks": int(weeks),
                "race_days": int(days),
                "heats": int(heats or 0),
                "results": int(results or 0),
                "horses": int(horses or 0),
            }
        )

    race_days = [
        {
            "race_day_id": r[0],
            "race_date_jalali": r[1],
            "race_date": r[2],
            "city": r[3],
            "track": r[4],
            "racecourse_code": r[5],
            "race_week_id": r[6],
            "heat_count": int(r[7]),
            "result_count": int(r[8]),
            "unique_horse_count": int(r[9]),
            "jalali_year": r[10],
        }
        for r in conn.execute(
            """
            SELECT race_day_id, race_date_jalali, race_date, city, track,
                   racecourse_code, race_week_id, heat_count, result_count,
                   unique_horse_count, jalali_year
            FROM wh_race_days
            ORDER BY race_date, track
            """
        )
    ]

    return {
        "overall": overall,
        "by_jalali_year": by_year,
        "race_days": race_days,
        "definitions": {
            "race_week": "Official competition week — ID from /racecards/{weekId}",
            "race_day": "Calendar day at a venue under a week — ID date|racecourse_code|week_id",
            "heat": "Individual course/round on a Race Day — never counted as Race Day",
            "result": "One horse performance row in a Heat (wh_race_results)",
            "horse": "wh_horses entity referenced by results",
        },
    }


def write_reports(stats: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": str(out_dir / "hierarchy_stats.json"),
        "md": str(out_dir / "hierarchy_stats.md"),
        "race_days_csv": str(out_dir / "race_days.csv"),
    }
    Path(paths["json"]).write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    o = stats["overall"]
    lines = [
        "# Racing Hierarchy Stats (recalculated)",
        "",
        "> Prior reports that treated `wh_races` / Heat as Race Day are **INVALID**.",
        "",
        "## Overall",
        "",
        f"- Race Weeks: **{o['race_weeks']}**",
        f"- Race Days: **{o['race_days']}**",
        f"- Individual Races / Heats: **{o['heats']}**",
        f"- Horses: **{o['horses']}**",
        f"- Results: **{o['results']}**",
        "",
        "## By Jalali year",
        "",
        "| سال شمسی | Race Weeks | Race Days | Heats | Results | Horses |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for y in stats["by_jalali_year"]:
        lines.append(
            f"| {y['jalali_year']} | {y['race_weeks']} | {y['race_days']} | "
            f"{y['heats']} | {y['results']} | {y['horses']} |"
        )
    lines.extend(
        [
            "",
            "## Per Race Day",
            "",
            "See `race_days.csv` (jalali date, gregorian date, city, race week, "
            "heat / result / unique horse counts).",
            "",
        ]
    )
    Path(paths["md"]).write_text("\n".join(lines), encoding="utf-8")

    import csv

    with open(paths["race_days_csv"], "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "race_date_jalali",
                "race_date",
                "city",
                "race_week_id",
                "heat_count",
                "result_count",
                "unique_horse_count",
                "racecourse_code",
                "track",
                "race_day_id",
                "jalali_year",
            ],
        )
        w.writeheader()
        for row in stats["race_days"]:
            w.writerow({k: row.get(k) for k in w.fieldnames})
    return paths
