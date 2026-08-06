"""Persistence helpers mapping domain models → ORM (optional for phase 1)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from src.database.models import HorseHistoryRecord, RaceHorseRecord, RaceRecord
from src.models import HorseHistory, Race


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def save_race(session: Session, race: Race, *, source: str = "asbdavani") -> RaceRecord:
    record = RaceRecord(
        source=source,
        source_id=race.source_id,
        source_url=race.source_url,
        name=race.race,
        race_date=_as_date(race.date),
        track=race.track,
        province=race.province,
        distance=race.distance,
        surface=race.surface,
        race_number=race.race_number,
        weather=race.weather,
        prize=race.prize if isinstance(race.prize, dict) else {"value": race.prize},
        raw=race.model_dump(mode="json", by_alias=True),
    )
    for horse in race.horses:
        record.horses.append(
            RaceHorseRecord(
                horse_source_id=horse.horse_id,
                name=horse.name,
                number=horse.number,
                age=horse.age,
                sex=horse.sex,
                weight=horse.weight,
                jockey=horse.jockey,
                trainer=horse.trainer,
                owner=horse.owner,
                rating=horse.rating,
                barrier=horse.barrier,
                finish_position=horse.finish_position,
                time=str(horse.time) if horse.time is not None else None,
                margin=horse.margin,
                odds=horse.odds,
                profile_url=horse.horse_profile_url,
            )
        )
    session.add(record)
    session.flush()
    logger.info("Saved race id={} source_id={}", record.id, record.source_id)
    return record


def save_horse_history(session: Session, history: HorseHistory) -> HorseHistoryRecord:
    record = HorseHistoryRecord(
        horse_source_id=history.horse.horse_id,
        horse_name=history.horse.name,
        profile_url=history.horse.profile_url,
        payload=history.model_dump(mode="json", by_alias=True),
    )
    session.add(record)
    session.flush()
    logger.info("Saved horse history id={} horse={!r}", record.id, record.horse_name)
    return record
