"""Module 4 — Race Classification.

Every race must have: distance, surface, class, age restriction, breed,
sex restriction, track condition, weather, race value, difficulty.
"""

from __future__ import annotations

import re
from typing import Any

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.analytics.metrics import (
    distance_bucket,
    parse_prize_map,
    parse_race_class,
)
from src.standardization.models import StdRaceClassification
from src.warehouse.models import WhRace, WhRaceResult, WhRaceWeather

_AGE_RE = re.compile(
    r"(?:(\d+)\s*ساله)|(?:(\d+)\s*year)|(?:age[s]?\s*(\d+))",
    re.I,
)
_SEX_RE = re.compile(
    r"(مادیان|نریان|filly|mare|colt|gelding|female|male|fillies|mares)",
    re.I,
)


REQUIRED_FIELDS = (
    "distance",
    "surface",
    "class_code",
    "age_restriction",
    "breed",
    "sex_restriction",
    "track_condition",
    "weather",
    "race_value",
    "difficulty",
)


def _parse_age_restriction(name: str | None) -> str | None:
    if not name:
        return None
    m = _AGE_RE.search(name)
    if not m:
        return None
    for g in m.groups():
        if g:
            return f"{g}yo"
    return None


def _parse_sex_restriction(name: str | None) -> str | None:
    if not name:
        return None
    m = _SEX_RE.search(name)
    return m.group(1).lower() if m else None


def _race_value(prize_json: Any) -> float | None:
    prize_map = parse_prize_map(prize_json)
    if not prize_map:
        return None
    return float(sum(prize_map.values()))


def _difficulty_proxy(session: Session, race_id: int) -> float | None:
    """Simple field-strength proxy: mean source_rating of entrants (0..100 scaled)."""
    ratings = [
        float(r)
        for r in session.scalars(
            select(WhRaceResult.source_rating).where(
                WhRaceResult.race_id == race_id,
                WhRaceResult.source_rating.is_not(None),
            )
        ).all()
        if r is not None
    ]
    if not ratings:
        return None
    return round(sum(ratings) / len(ratings), 4)


def classify_race(session: Session, race: WhRace) -> dict[str, Any]:
    weather_row = session.scalar(
        select(WhRaceWeather).where(WhRaceWeather.race_id == race.id)
    )
    track_condition = None
    weather = race.weather
    if weather_row is not None:
        track_condition = getattr(weather_row, "track_condition", None)
        weather = getattr(weather_row, "weather_condition", None) or weather

    class_code = parse_race_class(race.name)
    breed = race.surface  # asbdavani stores bloodline in surface
    payload = {
        "race_id": race.id,
        "distance": race.distance,
        "surface": race.surface,
        "going": track_condition,
        "class_code": class_code,
        "age_restriction": _parse_age_restriction(race.name),
        "breed": breed,
        "sex_restriction": _parse_sex_restriction(race.name),
        "track_condition": track_condition,
        "weather": weather,
        "race_value": _race_value(race.prize_json),
        "difficulty": _difficulty_proxy(session, race.id),
        "distance_bucket": distance_bucket(race.distance),
    }
    missing = [f for f in REQUIRED_FIELDS if payload.get(f) in (None, "", "unknown")]
    present = len(REQUIRED_FIELDS) - len(missing)
    payload["missing_fields"] = missing
    payload["completeness"] = present / len(REQUIRED_FIELDS)
    return payload


def build_race_classifications(
    session: Session,
    *,
    racecourse_code: str | None = None,
) -> dict[str, Any]:
    q = select(WhRace)
    if racecourse_code:
        q = q.where(WhRace.racecourse_code == racecourse_code)
    races = list(session.scalars(q).all())

    if racecourse_code:
        race_ids = [r.id for r in races]
        if race_ids:
            session.execute(
                delete(StdRaceClassification).where(
                    StdRaceClassification.race_id.in_(race_ids)
                )
            )
    else:
        session.execute(delete(StdRaceClassification))

    written = 0
    completeness_sum = 0.0
    for race in races:
        payload = classify_race(session, race)
        session.add(
            StdRaceClassification(
                race_id=payload["race_id"],
                distance=payload["distance"],
                surface=payload["surface"],
                going=payload["going"],
                class_code=payload["class_code"],
                age_restriction=payload["age_restriction"],
                breed=payload["breed"],
                sex_restriction=payload["sex_restriction"],
                track_condition=payload["track_condition"],
                weather=payload["weather"],
                race_value=payload["race_value"],
                difficulty=payload["difficulty"],
                distance_bucket=payload["distance_bucket"],
                completeness=payload["completeness"],
                missing_fields_json=payload["missing_fields"],
                meta_json={"source": "standardization.race_classification"},
            )
        )
        written += 1
        completeness_sum += float(payload["completeness"] or 0.0)

    session.flush()
    avg_c = completeness_sum / written if written else 0.0
    logger.info(
        "Race classifications written={} avg_completeness={:.2%}", written, avg_c
    )
    return {
        "races_classified": written,
        "avg_completeness": round(avg_c, 4),
    }
