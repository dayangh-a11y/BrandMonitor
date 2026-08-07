"""Raw-layer ingest: map collector domain models → warehouse Raw tables."""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.raw import RawHorse, RawHorseStart, RawIngestRun, RawRace, RawRaceEntry
from src.database.types_util import as_date
from src.models import HorseHistory, HorseProfile, Race


def start_ingest_run(
    session: Session,
    *,
    source: str,
    input_url: str | None = None,
) -> RawIngestRun:
    run = RawIngestRun(source=source, input_url=input_url, status="running")
    session.add(run)
    session.flush()
    return run


def finish_ingest_run(
    session: Session,
    run: RawIngestRun,
    *,
    status: str = "success",
    notes: str | None = None,
) -> RawIngestRun:
    run.status = status
    run.notes = notes
    run.finished_at = datetime.now(timezone.utc)
    session.flush()
    return run


def upsert_raw_horse(
    session: Session,
    *,
    source: str,
    source_horse_id: str,
    name: str,
    sex: str | None = None,
    birthdate=None,
    profile_url: str | None = None,
    sire: str | None = None,
    dam: str | None = None,
    payload: dict | None = None,
) -> RawHorse:
    stmt = select(RawHorse).where(
        RawHorse.source == source,
        RawHorse.source_horse_id == source_horse_id,
    )
    horse = session.scalar(stmt)
    if horse is None:
        horse = RawHorse(
            source=source,
            source_horse_id=source_horse_id,
            name=name,
        )
        session.add(horse)

    horse.name = name or horse.name
    if sex is not None:
        horse.sex = sex
    bd = as_date(birthdate)
    if bd is not None:
        horse.birthdate = bd
    if profile_url:
        horse.profile_url = profile_url
    if sire:
        horse.sire = sire
    if dam:
        horse.dam = dam
    if payload is not None:
        horse.payload_json = payload
    horse.last_seen_at = datetime.now(timezone.utc)
    session.flush()
    return horse


def ingest_race(
    session: Session,
    race: Race,
    *,
    source: str = "asbdavani",
    ingest_run: RawIngestRun | None = None,
) -> RawRace:
    """Upsert a collected race and its entries into Raw tables only."""
    payload = race.model_dump(mode="json", by_alias=True)
    source_race_id = race.source_id

    existing: RawRace | None = None
    if source_race_id:
        existing = session.scalar(
            select(RawRace).where(
                RawRace.source == source,
                RawRace.source_race_id == source_race_id,
            )
        )

    if existing is None:
        record = RawRace(
            source=source,
            source_race_id=source_race_id,
            ingest_run_id=ingest_run.id if ingest_run else None,
        )
        session.add(record)
    else:
        record = existing
        if ingest_run is not None:
            record.ingest_run_id = ingest_run.id
        # Replace entries on re-ingest for same race
        record.entries.clear()
        session.flush()

    record.source_url = race.source_url
    record.name = race.race
    record.race_date = as_date(race.date)
    record.track = race.track
    record.province = race.province
    record.distance = race.distance
    record.surface = race.surface
    record.race_number = race.race_number
    record.weather = race.weather
    record.prize_json = race.prize if isinstance(race.prize, dict) else (
        {"value": race.prize} if race.prize is not None else None
    )
    record.payload_json = payload
    record.collected_at = datetime.now(timezone.utc)
    session.flush()

    for horse in race.horses:
        raw_horse: RawHorse | None = None
        if horse.horse_id:
            raw_horse = upsert_raw_horse(
                session,
                source=source,
                source_horse_id=horse.horse_id,
                name=horse.name,
                sex=horse.sex,
                profile_url=horse.horse_profile_url,
                payload=horse.model_dump(mode="json", by_alias=True),
            )

        entry = RawRaceEntry(
            race_id=record.id,
            horse_id=raw_horse.id if raw_horse else None,
            source_horse_id=horse.horse_id,
            name=horse.name,
            number=horse.number,
            sex=horse.sex,
            weight=horse.weight,
            jockey=horse.jockey,
            trainer=horse.trainer,
            owner=horse.owner,
            source_rating=horse.rating,
            barrier=horse.barrier,
            finish_position=horse.finish_position,
            time_raw=str(horse.time) if horse.time is not None else None,
            margin=horse.margin,
            odds=horse.odds,
            profile_url=horse.horse_profile_url,
            payload_json=horse.model_dump(mode="json", by_alias=True),
        )
        # age is collector-derived → kept only inside payload_json, not as a Raw column
        session.add(entry)

    session.flush()
    logger.info(
        "Ingested raw race id={} source_id={} entries={}",
        record.id,
        record.source_race_id,
        len(race.horses),
    )
    return record


def ingest_horse_history(
    session: Session,
    history: HorseHistory,
    *,
    source: str = "asbdavani",
) -> RawHorse:
    """Upsert horse profile + historical starts into Raw tables only."""
    profile: HorseProfile = history.horse
    if not profile.horse_id:
        raise ValueError("Horse history requires horse_id for warehouse ingest")

    horse = upsert_raw_horse(
        session,
        source=source,
        source_horse_id=profile.horse_id,
        name=profile.name,
        sex=profile.sex,
        birthdate=profile.birthdate,
        profile_url=profile.profile_url,
        sire=profile.sire,
        dam=profile.dam,
        payload=profile.model_dump(mode="json", by_alias=True),
    )

    for row in history.history:
        race_date = as_date(row.race_date)
        stmt = select(RawHorseStart).where(
            RawHorseStart.source == source,
            RawHorseStart.source_horse_id == profile.horse_id,
            RawHorseStart.race_date == race_date,
            RawHorseStart.race_number == row.race_number,
            RawHorseStart.track == row.track,
            RawHorseStart.number == row.number,
        )
        start = session.scalar(stmt)
        if start is None:
            start = RawHorseStart(
                source=source,
                source_horse_id=profile.horse_id,
                horse_id=horse.id,
            )
            session.add(start)

        start.horse_id = horse.id
        start.race_name = row.race_name
        start.race_date = race_date
        start.track = row.track
        start.race_number = row.race_number
        start.distance = row.distance
        start.surface = row.surface
        start.number = row.number
        start.weight = row.weight
        start.jockey = row.jockey
        start.trainer = row.trainer
        start.owner = row.owner
        start.source_rating = row.rating
        start.barrier = row.barrier
        start.finish_position = row.finish_position
        start.time_raw = str(row.time) if row.time is not None else None
        start.margin = row.margin
        start.odds = row.odds
        start.race_url = row.race_url
        start.payload_json = row.model_dump(mode="json", by_alias=True)
        start.collected_at = datetime.now(timezone.utc)

    session.flush()
    logger.info(
        "Ingested raw horse history horse_id={} starts={}",
        horse.id,
        len(history.history),
    )
    return horse
