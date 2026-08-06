"""Parse asbdavani horse profile / history HTML."""

from __future__ import annotations

import re
from typing import Any

from loguru import logger

from src.asbdavani.constants import (
    BLOOD_SURFACE_HINT,
    absolute_url,
    format_race_time,
    normalize_sex,
    parse_horse_id_from_url,
)
from src.models import HorseHistory, HorseHistoryEntry, HorseProfile
from src.parsers.html import (
    extract_json_after_marker,
    extract_next_flight_text,
    safe_float,
    safe_int,
)
from src.utils.retry import ParseError


def _extract_history_payload(html: str) -> list[dict[str, Any]]:
    """
    Horse performance pages embed history as:
      {"data":{"data":[ {...raceHorse...}, ... ]}}
    inside the Next.js flight payload.
    """
    errors: list[str] = []

    # 1) Direct nested marker
    for marker in ('"data":{"data":', '"data":{ "data":'):
        try:
            obj = extract_json_after_marker(html, marker)
            rows = _coerce_history_rows(obj)
            if rows is not None:
                return rows
        except ParseError as exc:
            errors.append(str(exc))

    # 2) Search unescaped flight text for a data.data array of race rows
    flight = extract_next_flight_text(html)
    for m in re.finditer(r'"data"\s*:\s*\{\s*"data"\s*:\s*\[', flight):
        try:
            # Rewind to enclosing object start if possible
            start = flight.rfind("{", 0, m.start() + 1)
            if start < 0:
                start = m.start()
            from src.parsers.html import extract_balanced_json_value

            obj = extract_balanced_json_value(flight, start)
            rows = _coerce_history_rows(obj)
            if rows is not None:
                return rows
        except (ParseError, Exception) as exc:  # noqa: BLE001
            errors.append(str(exc))

    raise ParseError(
        "Unexpected horse history payload shape: " + "; ".join(errors[:3])
    )


def _coerce_history_rows(obj: Any) -> list[dict[str, Any]] | None:
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        if "race" in obj[0] or "entranceRating" in obj[0] or "horse" in obj[0]:
            return obj
    if isinstance(obj, dict):
        if isinstance(obj.get("data"), list):
            return _coerce_history_rows(obj["data"])
        inner = obj.get("data")
        if isinstance(inner, dict) and isinstance(inner.get("data"), list):
            return _coerce_history_rows(inner["data"])
    return None


def _extract_horse_profile_bits(
    html: str, url: str, history: list[dict[str, Any]]
) -> HorseProfile:
    horse_id = parse_horse_id_from_url(url)
    name = None
    sex = None
    birthdate = None
    sire = None
    dam = None

    for row in history:
        horse = row.get("horse") or {}
        if horse.get("name"):
            name = horse.get("name")
            sex = normalize_sex(horse.get("sex"))
            birthdate = horse.get("birthdate")
            father = horse.get("father") or {}
            mother = horse.get("mother") or {}
            sire = father.get("name")
            dam = mother.get("name")
            horse_id = horse_id or horse.get("id")
            break

    if not name:
        m = re.search(r'"@type":"ProfilePage","name":"([^"]+)"', html)
        if not m:
            m = re.search(r'\\"@type\\":\\"ProfilePage\\",\\"name\\":\\"([^\\"]+)\\"', html)
        if m:
            name = m.group(1)

    if not name:
        raise ParseError(f"Could not determine horse name for {url}")

    return HorseProfile(
        horseId=horse_id,
        name=name,
        sex=sex,
        birthdate=birthdate,
        profileUrl=url,
        sire=sire,
        dam=dam,
    )


def _history_entry(row: dict[str, Any]) -> HorseHistoryEntry:
    race = row.get("race") or {}
    week = race.get("week") or {}
    plan = race.get("plan") or {}
    coach = row.get("coach") or {}
    rider = row.get("rider") or {}
    extra = row.get("extra") or {}
    barrier = safe_int(extra.get("depar")) if isinstance(extra, dict) else None

    finish = row.get("rank")
    if finish == 0 and row.get("isRun") is False:
        finish_position = None
    else:
        finish_position = safe_int(finish)

    blood = plan.get("blood")
    surface = BLOOD_SURFACE_HINT.get(str(blood).upper(), blood) if blood else None

    week_id = week.get("id")
    race_round = race.get("round")
    race_url = None
    if week_id and race_round is not None:
        race_url = absolute_url(f"/racecards/{week_id}?round={race_round}")

    track = None
    week_name = week.get("name") or ""
    m = re.search(r"هفته\s+\d+\s+(.+?)\s+\d{4}", week_name)
    if m:
        track = m.group(1).strip()

    return HorseHistoryEntry(
        raceName=race.get("name") or plan.get("name") or week_name,
        raceDate=week.get("date"),
        track=track,
        raceNumber=safe_int(race_round),
        distance=safe_int(plan.get("distance")),
        surface=surface,
        number=safe_int(row.get("number")),
        weight=safe_float(row.get("weight")),
        jockey=(rider.get("name") if isinstance(rider, dict) else None),
        trainer=(coach.get("name") if isinstance(coach, dict) else None),
        owner=row.get("owner"),
        rating=safe_float(row.get("entranceRating")),
        barrier=barrier,
        finishPosition=finish_position,
        time=format_race_time(row.get("time")),
        margin=safe_float(row.get("dl")),
        odds=None,
        raceUrl=race_url,
    )


def parse_horse_history_html(html: str, url: str) -> HorseHistory:
    history_rows = _extract_history_payload(html)
    logger.info("Parsed {} history rows from {}", len(history_rows), url)
    profile = _extract_horse_profile_bits(html, url, history_rows)
    entries = [_history_entry(row) for row in history_rows]
    return HorseHistory(horse=profile, history=entries)


def parse_horse_profile_html(html: str, url: str) -> HorseProfile:
    try:
        history_rows = _extract_history_payload(html)
    except ParseError:
        history_rows = []
        logger.warning("No history payload while parsing horse profile {}", url)
    return _extract_horse_profile_bits(html, url, history_rows)
