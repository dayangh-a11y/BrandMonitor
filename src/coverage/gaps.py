"""Detect and persist Missing Coverage markers (never treat empty as 'no racing')."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

import jdatetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.coverage.models import CovMissingGap
from src.coverage.policy import DEFAULT_SOURCE_PRIORITIES
from src.utils.jalali import format_jalali
from src.warehouse.models import WhRace


SUGGESTED = [
    {"source": s, "rank": r, "note": n} for s, r, n in DEFAULT_SOURCE_PRIORITIES
]


def _month_bounds(jy: int, jm: int) -> tuple[date, date]:
    start = jdatetime.date(jy, jm, 1).togregorian()
    if jm <= 6:
        end = jdatetime.date(jy, jm, 31).togregorian()
    elif jm <= 11:
        end = jdatetime.date(jy, jm, 30).togregorian()
    else:
        leap = jdatetime.date(jy, 1, 1).isleap()
        end = jdatetime.date(jy, 12, 30 if leap else 29).togregorian()
    return start, end


def detect_and_upsert_missing_gaps(session: Session) -> dict[str, Any]:
    """
    Mark jalali year/month cells with zero heats in DB as Missing Coverage.

    Does NOT claim racing occurred — only that coverage is unverified/empty in DB.
    """
    races = session.scalars(select(WhRace).where(WhRace.race_date.is_not(None))).all()
    if not races:
        return {"upserted": 0, "open": 0}

    by_ym: dict[tuple[int, int], int] = defaultdict(int)
    by_ym_track: dict[tuple[int, int, str], int] = defaultdict(int)
    years: set[int] = set()
    tracks: set[str] = set()
    for r in races:
        g = r.race_date
        assert g is not None
        jd = jdatetime.date.fromgregorian(date=g)
        years.add(jd.year)
        by_ym[(jd.year, jd.month)] += 1
        if r.track:
            tracks.add(r.track)
            by_ym_track[(jd.year, jd.month, r.track)] += 1

    y_min, y_max = min(years), max(years)
    upserted = 0
    # Year-month nationwide voids
    for y in range(y_min, y_max + 1):
        for m in range(1, 13):
            if by_ym.get((y, m), 0) > 0:
                continue
            g0, g1 = _month_bounds(y, m)
            upserted += _upsert_gap(
                session,
                scope_type="month",
                jalali_year=y,
                jalali_month=m,
                track=None,
                breed=None,
                gregorian_start=g0,
                gregorian_end=g1,
                evidence={
                    "heats_in_db": 0,
                    "jalali_range": f"{y}/{m:02d}",
                    "gregorian_range": f"{g0.isoformat()}→{g1.isoformat()}",
                },
            )

    # City-month voids for known tracks (only months where nationwide has some racing
    # elsewhere — stronger signal of local missingness)
    for y in range(y_min, y_max + 1):
        for m in range(1, 13):
            if by_ym.get((y, m), 0) == 0:
                continue  # already marked nationwide
            for track in sorted(tracks):
                if by_ym_track.get((y, m, track), 0) > 0:
                    continue
                g0, g1 = _month_bounds(y, m)
                upserted += _upsert_gap(
                    session,
                    scope_type="city_month",
                    jalali_year=y,
                    jalali_month=m,
                    track=track,
                    breed=None,
                    gregorian_start=g0,
                    gregorian_end=g1,
                    evidence={
                        "heats_in_db_for_city_month": 0,
                        "nationwide_heats_same_month": by_ym[(y, m)],
                        "note": "سایر شهرها در این ماه داده دارند؛ این شهر خالی است — Missing Coverage",
                    },
                )

    session.flush()
    open_n = len(
        session.scalars(select(CovMissingGap).where(CovMissingGap.status == "open")).all()
    )
    return {
        "upserted_or_refreshed": upserted,
        "open_gaps": open_n,
        "span_jalali": f"{y_min}→{y_max}",
        "known_tracks": sorted(tracks),
    }


def _upsert_gap(
    session: Session,
    *,
    scope_type: str,
    jalali_year: int | None,
    jalali_month: int | None,
    track: str | None,
    breed: str | None,
    gregorian_start: date | None,
    gregorian_end: date | None,
    evidence: dict[str, Any],
) -> int:
    existing = session.scalar(
        select(CovMissingGap).where(
            CovMissingGap.scope_type == scope_type,
            CovMissingGap.jalali_year == jalali_year,
            CovMissingGap.jalali_month == jalali_month,
            CovMissingGap.track == track,
            CovMissingGap.breed == breed,
        )
    )
    if existing is None:
        session.add(
            CovMissingGap(
                scope_type=scope_type,
                jalali_year=jalali_year,
                jalali_month=jalali_month,
                track=track,
                breed=breed,
                gregorian_start=gregorian_start,
                gregorian_end=gregorian_end,
                status="open",
                evidence_json=evidence,
                suggested_sources_json=SUGGESTED,
                notes="Marked Missing Coverage — do not assume no races ran",
            )
        )
        return 1
    existing.evidence_json = evidence
    existing.suggested_sources_json = SUGGESTED
    existing.gregorian_start = gregorian_start
    existing.gregorian_end = gregorian_end
    if existing.status == "resolved" and evidence.get("heats_in_db", 0) == 0:
        existing.status = "open"
    return 0


def coverage_snapshot(session: Session) -> dict[str, Any]:
    races = session.scalars(select(WhRace)).all()
    days = {(r.race_date, r.track) for r in races if r.race_date and r.track}
    dates = sorted(r.race_date for r in races if r.race_date)
    return {
        "heats": len(races),
        "race_days": len(days),
        "first_jalali": format_jalali(dates[0]) if dates else None,
        "last_jalali": format_jalali(dates[-1]) if dates else None,
        "open_missing_gaps": len(
            session.scalars(select(CovMissingGap).where(CovMissingGap.status == "open")).all()
        ),
    }
