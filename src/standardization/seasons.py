"""Module 3 — Season Engine.

Season must have: season_id, start_date, end_date, track, country, year.
No hardcoded season keys.
"""

from __future__ import annotations

import hashlib
from typing import Any

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.analytics.seasons import SeasonCluster, discover_seasons
from src.standardization.constants import DEFAULT_COUNTRY
from src.standardization.models import StdSeason


def make_season_id(
    *,
    country: str,
    racecourse_code: str | None,
    start_date,
    end_date,
    year: int,
) -> str:
    """
    Deterministic permanent season_id (not a hardcoded calendar label).

    Format: {country}-{track}-{year}-{short_hash}
    """
    track = (racecourse_code or "unknown").strip().lower().replace(" ", "-")
    payload = f"{country}|{track}|{start_date.isoformat()}|{end_date.isoformat()}|{year}"
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]
    return f"{country.lower()}-{track}-{year}-{digest}"


def sync_standardized_seasons(
    session: Session,
    *,
    racecourse_code: str | None = None,
    country: str = DEFAULT_COUNTRY,
) -> list[dict[str, Any]]:
    """Discover seasons from warehouse dates and persist std_seasons."""
    clusters: list[SeasonCluster] = discover_seasons(
        session, racecourse_code=racecourse_code
    )
    # Replace registry for scoped courses (full rebuild of std_seasons for scope)
    if racecourse_code:
        session.execute(
            delete(StdSeason).where(StdSeason.racecourse_code == racecourse_code)
        )
    else:
        session.execute(delete(StdSeason))

    out: list[dict[str, Any]] = []
    for c in clusters:
        year = c.start_date.year
        season_id = make_season_id(
            country=country,
            racecourse_code=c.racecourse_code,
            start_date=c.start_date,
            end_date=c.end_date,
            year=year,
        )
        track = c.racecourse_code or "unknown"
        row = StdSeason(
            season_id=season_id,
            start_date=c.start_date,
            end_date=c.end_date,
            track=track,
            country=country,
            year=year,
            racecourse_code=c.racecourse_code,
            label=c.label,
            is_completed=c.is_completed,
            is_latest_completed=c.is_latest_completed,
            race_days=c.race_days,
            heats=c.heats,
            legacy_season_key=c.season_key,
            meta_json={
                "discovery": "gap_cluster",
                "legacy_season_key": c.season_key,
            },
        )
        session.add(row)
        out.append(
            {
                "season_id": season_id,
                "start_date": c.start_date.isoformat(),
                "end_date": c.end_date.isoformat(),
                "track": track,
                "country": country,
                "year": year,
                "legacy_season_key": c.season_key,
                "is_completed": c.is_completed,
                "is_latest_completed": c.is_latest_completed,
            }
        )
    session.flush()
    logger.info("Standardized seasons synced: {}", len(out))
    return out


def get_season(session: Session, season_id: str) -> StdSeason | None:
    return session.scalar(select(StdSeason).where(StdSeason.season_id == season_id))


def list_seasons(
    session: Session,
    *,
    track: str | None = None,
    year: int | None = None,
) -> list[StdSeason]:
    q = select(StdSeason).order_by(StdSeason.start_date.desc())
    if track:
        q = q.where(StdSeason.track == track)
    if year:
        q = q.where(StdSeason.year == year)
    return list(session.scalars(q).all())
