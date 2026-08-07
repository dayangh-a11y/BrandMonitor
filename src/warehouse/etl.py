"""ETL: current Raw versions → normalized Warehouse tables."""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.raw import RawHorse, RawRace, RawRaceEntry
from src.warehouse.models import (
    WhHorse,
    WhHorsePedigree,
    WhJockey,
    WhOwner,
    WhRace,
    WhRaceResult,
    WhRaceVideo,
    WhTrainer,
)


def _get_or_create_person(session: Session, model, name: str | None):
    if not name or not str(name).strip():
        return None
    cleaned = str(name).strip()
    row = session.scalar(select(model).where(model.name == cleaned))
    if row is None:
        row = model(name=cleaned)
        session.add(row)
        session.flush()
    return row


def _upsert_horse(session: Session, raw: RawHorse) -> WhHorse:
    horse = session.scalar(
        select(WhHorse).where(
            WhHorse.source == raw.source,
            WhHorse.source_horse_id == raw.source_horse_id,
        )
    )
    if horse is None:
        horse = WhHorse(source=raw.source, source_horse_id=raw.source_horse_id, name=raw.name)
        session.add(horse)
    horse.name = raw.name
    horse.sex = raw.sex
    horse.birthdate = raw.birthdate
    horse.profile_url = raw.profile_url
    horse.raw_horse_id = raw.id
    horse.updated_at = datetime.now(timezone.utc)
    session.flush()

    # Pedigree shell (names only — no analysis)
    ped = session.scalar(select(WhHorsePedigree).where(WhHorsePedigree.horse_id == horse.id))
    if ped is None:
        ped = WhHorsePedigree(horse_id=horse.id)
        session.add(ped)
    ped.sire_name = raw.sire
    ped.dam_name = raw.dam
    ped.updated_at = datetime.now(timezone.utc)
    session.flush()
    return horse


def _upsert_race(session: Session, raw: RawRace) -> WhRace:
    race = session.scalar(
        select(WhRace).where(
            WhRace.source == raw.source,
            WhRace.source_race_id == raw.source_race_id,
        )
    )
    if race is None:
        race = WhRace(source=raw.source, source_race_id=raw.source_race_id)
        session.add(race)
    race.name = raw.name
    race.race_date = raw.race_date
    race.track = raw.track
    race.racecourse_code = raw.racecourse_code
    race.province = raw.province
    race.distance = raw.distance
    race.surface = raw.surface
    race.race_number = raw.race_number
    race.weather = raw.weather
    race.prize_json = raw.prize_json
    race.source_url = raw.source_url
    race.raw_race_id = raw.id
    race.updated_at = datetime.now(timezone.utc)
    session.flush()

    # Videos from payload media if present (structure only)
    media = []
    if isinstance(raw.payload_json, dict):
        # best-effort nested search
        for key in ("media", "videos"):
            if isinstance(raw.payload_json.get(key), list):
                media = raw.payload_json[key]
                break
    if media:
        existing_urls = {v.url for v in race.videos}
        for item in media:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not url or url in existing_urls:
                continue
            session.add(
                WhRaceVideo(
                    race_id=race.id,
                    url=url,
                    title=item.get("title") or item.get("name"),
                    media_type=item.get("type"),
                )
            )
        session.flush()
    return race


def build_warehouse(session: Session) -> dict[str, int]:
    """Rebuild curated warehouse rows from is_current Raw extracts."""
    stats = {"horses": 0, "races": 0, "results": 0, "jockeys": 0, "trainers": 0, "owners": 0}

    for raw_horse in session.scalars(select(RawHorse).where(RawHorse.is_current.is_(True))):
        _upsert_horse(session, raw_horse)
        stats["horses"] += 1

    for raw_race in session.scalars(select(RawRace).where(RawRace.is_current.is_(True))):
        race = _upsert_race(session, raw_race)
        stats["races"] += 1

        # Replace results for this race from current raw entries
        for old in session.scalars(select(WhRaceResult).where(WhRaceResult.race_id == race.id)):
            session.delete(old)
        session.flush()

        for entry in session.scalars(
            select(RawRaceEntry).where(
                RawRaceEntry.race_id == raw_race.id,
                RawRaceEntry.is_current.is_(True),
            )
        ):
            horse = None
            if entry.source_horse_id:
                horse = session.scalar(
                    select(WhHorse).where(
                        WhHorse.source == raw_race.source,
                        WhHorse.source_horse_id == entry.source_horse_id,
                    )
                )
            jockey = _get_or_create_person(session, WhJockey, entry.jockey)
            trainer = _get_or_create_person(session, WhTrainer, entry.trainer)
            owner = _get_or_create_person(session, WhOwner, entry.owner)
            session.add(
                WhRaceResult(
                    race_id=race.id,
                    horse_id=horse.id if horse else None,
                    jockey_id=jockey.id if jockey else None,
                    trainer_id=trainer.id if trainer else None,
                    owner_id=owner.id if owner else None,
                    number=entry.number,
                    weight=entry.weight,
                    source_rating=entry.source_rating,
                    barrier=entry.barrier,
                    finish_position=entry.finish_position,
                    time_raw=entry.time_raw,
                    margin=entry.margin,
                    odds=entry.odds,
                    raw_entry_id=entry.id,
                )
            )
            stats["results"] += 1

    stats["jockeys"] = len(list(session.scalars(select(WhJockey.id)).all()))
    stats["trainers"] = len(list(session.scalars(select(WhTrainer.id)).all()))
    stats["owners"] = len(list(session.scalars(select(WhOwner.id)).all()))
    session.flush()
    logger.info("Warehouse build complete {}", stats)
    return stats
