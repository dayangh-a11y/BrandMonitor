"""Parse asbdavani racecard / race HTML into Race models."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse

from loguru import logger

from src.asbdavani.constants import (
    BASE_URL,
    BLOOD_SURFACE_HINT,
    absolute_url,
    compute_age,
    format_race_time,
    horse_profile_url,
    location_from_week_and_leagues,
    normalize_race_media,
    normalize_sex,
    parse_race_url,
    prize_summary,
)
from src.models import HorseEntry, Race
from src.parsers.html import extract_json_after_marker, find_all_hrefs, safe_float, safe_int
from src.racecourses import ensure_racecourse
from src.utils.retry import ParseError


def _race_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _find_race(week: dict[str, Any], race_round: int | None) -> dict[str, Any]:
    races = week.get("races") or []
    if not races:
        raise ParseError("No races found in week payload")
    if race_round is None:
        # Default to first race by round number
        return sorted(races, key=lambda r: r.get("round") or 0)[0]
    for race in races:
        if race.get("round") == race_round:
            return race
    available = sorted({r.get("round") for r in races})
    raise ParseError(f"Round {race_round} not found. Available rounds: {available}")


def _horse_entry(
    race_horse: dict[str, Any],
    *,
    on_date: date | None,
) -> HorseEntry:
    horse = race_horse.get("horse") or {}
    horse_id = horse.get("id")
    coach = race_horse.get("coach") or {}
    rider = race_horse.get("rider") or {}
    extra = race_horse.get("extra") or {}
    barrier = safe_int(extra.get("depar")) if isinstance(extra, dict) else None

    finish = race_horse.get("rank")
    # rank 0 with isRun False typically means scratched / DNS
    if finish == 0 and race_horse.get("isRun") is False:
        finish_position = None
    else:
        finish_position = safe_int(finish)

    return HorseEntry(
        name=horse.get("name") or "UNKNOWN",
        number=safe_int(race_horse.get("number")),
        age=compute_age(horse.get("birthdate"), on=on_date),
        sex=normalize_sex(horse.get("sex")),
        weight=safe_float(race_horse.get("weight")),
        jockey=(rider.get("name") if isinstance(rider, dict) else None) or None,
        trainer=(coach.get("name") if isinstance(coach, dict) else None) or None,
        owner=race_horse.get("owner")
        or ((horse.get("owner") or {}).get("name") if isinstance(horse.get("owner"), dict) else None),
        rating=safe_float(race_horse.get("entranceRating")),
        barrier=barrier,
        finishPosition=finish_position,
        time=format_race_time(race_horse.get("time")),
        margin=safe_float(race_horse.get("dl")),
        odds=None,
        horseProfileUrl=horse_profile_url(horse_id) if horse_id else None,
        horseId=horse_id,
    )


def parse_race_html(html: str, url: str) -> Race:
    """Extract Race model from asbdavani racecards page HTML."""
    week_id, race_round = parse_race_url(url)
    try:
        week = extract_json_after_marker(html, '_weekInfo":')
    except ParseError:
        week = extract_json_after_marker(html, '"_weekInfo":')

    # leagues may be sibling props in the same RSC payload; best-effort extract
    leagues: list[dict[str, Any]] | None = None
    try:
        leagues_obj = extract_json_after_marker(html, '"leagues":')
        if isinstance(leagues_obj, list):
            leagues = leagues_obj
    except ParseError:
        # leagues marker extraction is best-effort; week payload is enough
        logger.debug("Could not extract leagues list from page")

    race_raw = _find_race(week, race_round)
    plan = race_raw.get("plan") or {}
    blood = plan.get("blood")
    surface = BLOOD_SURFACE_HINT.get(str(blood).upper(), blood) if blood else None
    location = location_from_week_and_leagues(week, leagues)
    if not location:
        raise ParseError(f"Racecourse (track) missing for race URL {url!r}")
    course = ensure_racecourse(location)
    track_name = course.name_fa
    racecourse_code = course.code

    race_date = week.get("date")
    on_date = _race_date(race_date)

    horses = [
        _horse_entry(rh, on_date=on_date)
        for rh in (race_raw.get("raceHorses") or [])
    ]
    horses.sort(key=lambda h: (h.number is None, h.number or 0))

    return Race(
        race=race_raw.get("name") or plan.get("name"),
        date=race_date,
        track=track_name,
        racecourse_code=racecourse_code,
        province=track_name,
        distance=safe_int(plan.get("distance")),
        surface=surface,
        raceNumber=safe_int(race_raw.get("round")),
        weather=None,
        prize=prize_summary(race_raw.get("prize")),
        media=normalize_race_media(race_raw.get("media")),
        sourceUrl=url,
        sourceId=race_raw.get("id") or week_id,
        horses=horses,
    )


def parse_race_list_html(html: str, base_url: str = BASE_URL) -> list[dict[str, str]]:
    """Collect racecard links from the listing page."""
    hrefs = find_all_hrefs(html, r"/racecards/[A-Za-z0-9]+")
    seen: set[str] = set()
    items: list[dict[str, str]] = []
    for href in hrefs:
        full = absolute_url(href)
        parsed = urlparse(full)
        # normalize without fragment
        key = urlunparse(parsed._replace(fragment=""))
        if key in seen:
            continue
        seen.add(key)
        week_id, _ = parse_race_url(key)
        items.append({"url": key, "sourceId": week_id or "", "title": ""})
    return items


def build_race_url(week_id: str, race_round: int) -> str:
    path = f"/racecards/{week_id}"
    return absolute_url(f"{path}?{urlencode({'round': race_round})}")
