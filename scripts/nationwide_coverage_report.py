"""Nationwide coverage report + random 100-horse career audit.

Run after warehouse rebuild + identity build.
"""

from __future__ import annotations

import json
import os
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB_PATH = Path("/workspace/output/historical/horse_racing.db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{DB_PATH}")

from sqlalchemy import func, select, text

from src.database import reset_engine, session_scope
from src.identity.models import IdHorse, IdHorseLink, IdHorseMergeCandidate
from src.identity.normalize import normalize_name
from src.utils.settings import get_settings
from src.warehouse.models import WhHorse, WhRace, WhRaceResult

ARTIFACTS = Path("/opt/cursor/artifacts")
ARTIFACTS.mkdir(parents=True, exist_ok=True)

EXPECTED_INDEX_WEEKS = 182
TARGET_BREEDS = ("Turkmen", "Thoroughbred", "Arab", "Crossbred", "DoKhoon")


def _breed_from_surface(surface: str | None) -> str:
    if not surface:
        return "unknown"
    s = str(surface).strip().lower()
    mapping = {
        "turkmen": "Turkmen",
        "thoroughbred": "Thoroughbred",
        "arab": "Arab",
        "arabian": "Arab",
        "crossbred": "Crossbred",
        "dokhoon": "Crossbred",
        "do khoon": "Crossbred",
        "دوخون": "Crossbred",
        "ترکمن": "Turkmen",
        "تروبرد": "Thoroughbred",
        "thorough": "Thoroughbred",
        "انجلیش": "Thoroughbred",
        "انگلیش": "Thoroughbred",
        "عرب": "Arab",
    }
    for key, label in mapping.items():
        if key in s:
            return label
    return surface


def build_report(session) -> dict:
    weeks = int(
        session.execute(
            text(
                "SELECT COUNT(*) FROM crawl_jobs "
                "WHERE job_type='week' AND status IN ('success','skipped_unchanged')"
            )
        ).scalar()
        or 0
    )
    races = int(session.scalar(select(func.count()).select_from(WhRace)) or 0)
    horses = int(session.scalar(select(func.count()).select_from(WhHorse)) or 0)
    permanent = int(session.scalar(select(func.count()).select_from(IdHorse)) or 0)
    links = int(session.scalar(select(func.count()).select_from(IdHorseLink)) or 0)
    open_cand = int(
        session.scalar(
            select(func.count())
            .select_from(IdHorseMergeCandidate)
            .where(IdHorseMergeCandidate.status == "open")
        )
        or 0
    )

    # Merged: permanent IDs with >1 warehouse link
    merge_rows = session.execute(
        text(
            "SELECT horse_id, COUNT(*) AS n FROM id_horse_links "
            "GROUP BY horse_id HAVING n > 1"
        )
    ).fetchall()
    horses_merged = len(merge_rows)
    warehouse_rows_merged = sum(int(n) for _, n in merge_rows)

    # Unresolved: warehouse horses without identity link
    linked_wh = {
        int(r[0])
        for r in session.execute(text("SELECT warehouse_horse_id FROM id_horse_links")).fetchall()
    }
    all_wh = list(session.scalars(select(WhHorse.id)).all())
    unresolved = [hid for hid in all_wh if hid not in linked_wh]

    # Horses by city (via race results)
    by_city: Counter[str] = Counter()
    horse_cities: dict[int, set[str]] = defaultdict(set)
    for hid, code in session.execute(
        text(
            """
            SELECT rr.horse_id, r.racecourse_code
            FROM wh_race_results rr
            JOIN wh_races r ON r.id = rr.race_id
            WHERE rr.horse_id IS NOT NULL AND r.racecourse_code IS NOT NULL
            """
        )
    ):
        by_city[str(code)] += 1
        horse_cities[int(hid)].add(str(code))

    horses_by_city = {
        city: len({h for h, cities in horse_cities.items() if city in cities})
        for city in sorted(by_city)
    }

    # Breed via race surface of starts
    breed_starts: Counter[str] = Counter()
    horse_breeds: dict[int, Counter[str]] = defaultdict(Counter)
    for hid, surface in session.execute(
        text(
            """
            SELECT rr.horse_id, r.surface
            FROM wh_race_results rr
            JOIN wh_races r ON r.id = rr.race_id
            WHERE rr.horse_id IS NOT NULL
            """
        )
    ):
        breed = _breed_from_surface(surface)
        breed_starts[breed] += 1
        horse_breeds[int(hid)][breed] += 1

    horses_by_breed: Counter[str] = Counter()
    for hid, counts in horse_breeds.items():
        primary = counts.most_common(1)[0][0] if counts else "unknown"
        horses_by_breed[primary] += 1

    coverage = round(100.0 * weeks / EXPECTED_INDEX_WEEKS, 2) if EXPECTED_INDEX_WEEKS else None

    # Duplicate candidates sample
    cand_sample = []
    for row in session.scalars(
        select(IdHorseMergeCandidate)
        .where(IdHorseMergeCandidate.status == "open")
        .order_by(IdHorseMergeCandidate.score.desc())
        .limit(25)
    ).all():
        cand_sample.append(
            {
                "left_horse_id": row.left_horse_id,
                "right_horse_id": row.right_horse_id,
                "score": round(float(row.score), 4),
                "status": row.status,
            }
        )

    return {
        "at": datetime.now(timezone.utc).isoformat(),
        "total_weeks_collected": weeks,
        "expected_index_weeks": EXPECTED_INDEX_WEEKS,
        "coverage_percentage": coverage,
        "total_races": races,
        "total_horses_warehouse": horses,
        "total_permanent_horse_ids": permanent,
        "identity_links": links,
        "horses_merged": horses_merged,
        "warehouse_rows_in_merged_clusters": warehouse_rows_merged,
        "unresolved_horses": len(unresolved),
        "unresolved_horse_ids_sample": unresolved[:50],
        "duplicate_candidates": open_cand,
        "duplicate_candidates_sample": cand_sample,
        "horses_by_breed": dict(horses_by_breed.most_common()),
        "horses_by_city": horses_by_city,
        "starts_by_city": dict(by_city.most_common()),
        "target_breeds": list(TARGET_BREEDS),
    }


def audit_100_horses(session, *, seed: int = 42) -> dict:
    """
    Randomly select 100 permanent horses and verify national career completeness:
    every race start linked to that permanent horse_id is present with date and
    city, spanning every racecourse where this identity started.
    """
    horse_ids = list(
        session.scalars(select(IdHorse.horse_id).where(IdHorse.status == "active")).all()
    )
    rng = random.Random(seed)
    sample_n = min(100, len(horse_ids))
    sample = rng.sample(horse_ids, sample_n) if horse_ids else []

    week_dates = {
        r[0]
        for r in session.execute(
            text("SELECT DISTINCT race_date FROM wh_races WHERE race_date IS NOT NULL")
        ).fetchall()
        if r[0] is not None
    }

    results = []
    complete = 0
    for hid in sample:
        wh_ids = [
            int(x)
            for x in session.execute(
                text("SELECT warehouse_horse_id FROM id_horse_links WHERE horse_id=:h"),
                {"h": hid},
            ).scalars()
        ]
        if not wh_ids:
            results.append(
                {
                    "horse_id": hid,
                    "complete": False,
                    "reason": "no_warehouse_links",
                }
            )
            continue

        placeholders = ",".join(str(i) for i in wh_ids)
        starts = session.execute(
            text(
                f"""
                SELECT r.race_date, r.racecourse_code, r.track, r.id
                FROM wh_race_results rr
                JOIN wh_races r ON r.id = rr.race_id
                WHERE rr.horse_id IN ({placeholders})
                ORDER BY r.race_date
                """
            )
        ).fetchall()

        cities = sorted({str(s[1]) for s in starts if s[1]})
        dates = [s[0] for s in starts if s[0] is not None]
        missing_dates = sum(1 for s in starts if s[0] is None)
        missing_cities = sum(1 for s in starts if not s[1])

        # Every linked warehouse row should contribute ≥0 starts; career is
        # complete when all starts have date+city and at least one start exists
        # (maiden/unraced warehouse-only rows are incomplete).
        links_with_starts = {
            int(x)
            for x in session.execute(
                text(
                    f"""
                    SELECT DISTINCT rr.horse_id FROM wh_race_results rr
                    WHERE rr.horse_id IN ({placeholders})
                    """
                )
            ).scalars()
        }
        orphan_links = [i for i in wh_ids if i not in links_with_starts]

        horse = session.get(IdHorse, hid)
        is_complete = (
            len(starts) > 0
            and missing_dates == 0
            and missing_cities == 0
            and not orphan_links
        )
        if is_complete:
            complete += 1
        results.append(
            {
                "horse_id": hid,
                "display_name": horse.display_name if horse else None,
                "warehouse_ids": wh_ids,
                "starts": len(starts),
                "cities": cities,
                "city_count": len(cities),
                "first_date": str(dates[0]) if dates else None,
                "last_date": str(dates[-1]) if dates else None,
                "missing_dates": missing_dates,
                "missing_cities": missing_cities,
                "orphan_warehouse_links": orphan_links,
                "complete": is_complete,
            }
        )

    multi_city = sum(1 for r in results if r.get("city_count", 0) >= 2)
    return {
        "seed": seed,
        "sampled": sample_n,
        "complete": complete,
        "incomplete": sample_n - complete,
        "complete_pct": round(100.0 * complete / sample_n, 2) if sample_n else None,
        "multi_city_careers_in_sample": multi_city,
        "horses": results,
        "warehouse_race_dates_indexed": len(week_dates),
    }


def main() -> None:
    reset_engine()
    settings = get_settings()
    with session_scope(settings) as session:
        report = build_report(session)
        audit = audit_100_horses(session)

    payload = {"coverage": report, "national_career_audit_100": audit}
    out = ARTIFACTS / "nationwide_coverage_report.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Nationwide career database — coverage report",
        "",
        f"- **Total weeks collected:** {report['total_weeks_collected']} / {report['expected_index_weeks']}",
        f"- **Coverage percentage:** {report['coverage_percentage']}%",
        f"- **Total races:** {report['total_races']}",
        f"- **Total horses (warehouse):** {report['total_horses_warehouse']}",
        f"- **Permanent horse_ids:** {report['total_permanent_horse_ids']}",
        f"- **Horses merged (multi-link IDs):** {report['horses_merged']}",
        f"- **Unresolved horses:** {report['unresolved_horses']}",
        f"- **Duplicate candidates:** {report['duplicate_candidates']}",
        f"- **Horses by breed:** {report['horses_by_breed']}",
        f"- **Horses by city:** {report['horses_by_city']}",
        "",
        "## Random 100-horse national career audit",
        f"- Sampled: {audit['sampled']}",
        f"- Complete: {audit['complete']} ({audit['complete_pct']}%)",
        f"- Incomplete: {audit['incomplete']}",
        "",
    ]
    text_path = ARTIFACTS / "nationwide_coverage_report.md"
    text_path.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines), flush=True)
    print(f"Wrote {out}", flush=True)


if __name__ == "__main__":
    main()
