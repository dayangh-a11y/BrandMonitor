"""Deterministic hierarchy keys from reliable DB / source fields only.

No guessed IDs. Missing inputs → None (incomplete link), never synthetic UUIDs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import parse_qs, urlparse


@dataclass(frozen=True, slots=True)
class RaceWeekRef:
    """Official competition week / meeting period on the source."""

    week_id: str
    source: str = "asbdavani"

    @property
    def race_week_id(self) -> str:
        return self.week_id


@dataclass(frozen=True, slots=True)
class RaceDayRef:
    """One calendar day of racing at one venue, tied to a Race Week when known."""

    race_day_id: str
    race_date: date
    racecourse_code: str
    track: str
    week_id: str | None


@dataclass(frozen=True, slots=True)
class HeatRef:
    """One independent course (round) on a Race Day."""

    heat_key: str
    source_race_id: str | None
    week_id: str | None
    race_number: int | None
    race_day_id: str | None


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    if len(text) < 10:
        return None
    try:
        y, m, d = map(int, text.split("-"))
        return date(y, m, d)
    except ValueError:
        return None


def derive_week_id(source_url: str | None) -> str | None:
    """Race Week ID = `/racecards/{weekId}` path segment from a real source URL."""
    if not source_url:
        return None
    parsed = urlparse(str(source_url).strip())
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "racecards" and parts[1]:
        return parts[1]
    return None


def derive_round_from_url(source_url: str | None) -> int | None:
    if not source_url:
        return None
    qs = parse_qs(urlparse(str(source_url).strip()).query)
    raw = (qs.get("round") or [None])[0]
    if raw is None or not str(raw).isdigit():
        return None
    return int(raw)


def derive_race_day_id(
    *,
    race_date: date | str | None,
    racecourse_code: str | None,
    week_id: str | None,
    track: str | None = None,
) -> str | None:
    """Race Day ID from reliable fields: Gregorian date + venue code + Race Week.

    Format: ``{YYYY-MM-DD}|{racecourse_code}|{week_id}``

    If ``week_id`` is missing, falls back to ``{YYYY-MM-DD}|{racecourse_code}``
    only when date and venue code are both present (still a real Race Day;
    week link incomplete). Never invents week or venue.
    """
    on = _as_date(race_date)
    code = (racecourse_code or "").strip()
    if not code and track:
        # Venue code is preferred; track name alone is not used as ID material
        # unless code is absent — then track is the only stored venue field.
        code = str(track).strip()
    if on is None or not code:
        return None
    wid = (week_id or "").strip()
    if wid:
        return f"{on.isoformat()}|{code}|{wid}"
    return f"{on.isoformat()}|{code}"


def derive_heat_key(
    *,
    source_race_id: str | None,
    week_id: str | None,
    race_number: int | None,
    source_url: str | None = None,
) -> str | None:
    """Canonical Heat key from source identifiers — never a random guess.

    Preference:
    1. ``source_race_id`` when it is present and is NOT identical to bare ``week_id``
       (bare week_id collides across heats in the same week).
    2. ``{week_id}|round={N}`` from URL round or ``race_number`` when both exist.
    3. Otherwise None (incomplete — do not invent).
    """
    wid = (week_id or derive_week_id(source_url) or "").strip() or None
    rnd = race_number if race_number is not None else derive_round_from_url(source_url)
    sid = (source_race_id or "").strip() or None

    if sid and sid != wid:
        return sid
    if wid and rnd is not None:
        return f"{wid}|round={int(rnd)}"
    if sid:
        # Only bare week_id available — not a valid unique heat key.
        return None
    return None


def heat_ref_from_row(
    *,
    source_race_id: str | None,
    source_url: str | None,
    race_date: date | str | None,
    racecourse_code: str | None,
    track: str | None,
    race_number: int | None,
) -> HeatRef:
    week_id = derive_week_id(source_url)
    rnd = race_number if race_number is not None else derive_round_from_url(source_url)
    race_day_id = derive_race_day_id(
        race_date=race_date,
        racecourse_code=racecourse_code,
        week_id=week_id,
        track=track,
    )
    return HeatRef(
        heat_key=derive_heat_key(
            source_race_id=source_race_id,
            week_id=week_id,
            race_number=rnd,
            source_url=source_url,
        )
        or "",
        source_race_id=source_race_id,
        week_id=week_id,
        race_number=rnd,
        race_day_id=race_day_id,
    )
