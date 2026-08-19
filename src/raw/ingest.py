"""Append-only Raw ingest — never overwrites prior extract versions."""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.raw import (
    RawHorse,
    RawHorseStart,
    RawIngestRun,
    RawParserError,
    RawRace,
    RawRaceEntry,
)
from src.coverage.dates import jalali_string
from src.database.types_util import as_date
from src.models import HorseHistory, HorseProfile, Race
from src.versioning import PARSER_VERSION
from src.versioning.hashing import compute_source_hash
from src.versioning.policy import now_utc, prepare_append


def start_ingest_run(
    session: Session,
    *,
    source: str,
    input_url: str | None = None,
    parser_version: str = PARSER_VERSION,
) -> RawIngestRun:
    run = RawIngestRun(
        source=source,
        input_url=input_url,
        status="running",
        parser_version=parser_version,
    )
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


def record_parser_error(
    session: Session,
    *,
    error_type: str,
    message: str,
    source: str | None = None,
    source_url: str | None = None,
    payload: dict | None = None,
    parser_version: str = PARSER_VERSION,
) -> RawParserError:
    row = RawParserError(
        source=source,
        source_url=source_url,
        parser_version=parser_version,
        error_type=error_type,
        message=message[:4000],
        payload_json=payload,
    )
    session.add(row)
    session.flush()
    return row


def append_raw_horse(
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
    source_url: str | None = None,
    parser_version: str = PARSER_VERSION,
) -> RawHorse:
    """Append a horse version if hash changed; return current horse row."""
    payload = payload or {
        "source_horse_id": source_horse_id,
        "name": name,
        "sex": sex,
        "birthdate": str(birthdate) if birthdate else None,
        "profile_url": profile_url,
        "sire": sire,
        "dam": dam,
    }
    row = prepare_append(
        session,
        model=RawHorse,
        identity_filters=[
            RawHorse.source == source,
            RawHorse.source_horse_id == source_horse_id,
        ],
        payload=payload,
        source_url=source_url or profile_url,
        parser_version=parser_version,
        field_values={
            "source": source,
            "source_horse_id": source_horse_id,
            "name": name,
            "sex": sex,
            "birthdate": as_date(birthdate),
            "profile_url": profile_url,
            "sire": sire,
            "dam": dam,
            "payload_json": payload,
        },
    )
    if row is not None:
        return row
    current = session.scalar(
        select(RawHorse).where(
            RawHorse.source == source,
            RawHorse.source_horse_id == source_horse_id,
            RawHorse.is_current.is_(True),
        )
    )
    assert current is not None
    return current


def ingest_race(
    session: Session,
    race: Race,
    *,
    source: str = "asbdavani",
    ingest_run: RawIngestRun | None = None,
    parser_version: str = PARSER_VERSION,
) -> RawRace | None:
    """
    Append a new Raw race version when content changes.

    Prior versions and their entries are preserved (never overwritten).
    """
    payload = race.model_dump(mode="json", by_alias=True)
    source_race_id = race.source_id
    if not source_race_id:
        record_parser_error(
            session,
            error_type="missing_source_id",
            message="Race payload missing sourceId",
            source=source,
            source_url=race.source_url,
            payload=payload,
            parser_version=parser_version,
        )

    identity = [
        RawRace.source == source,
        RawRace.source_race_id == source_race_id,
    ]
    new_race = prepare_append(
        session,
        model=RawRace,
        identity_filters=identity,
        payload=payload,
        source_url=race.source_url,
        parser_version=parser_version,
        field_values={
            "ingest_run_id": ingest_run.id if ingest_run else None,
            "source": source,
            "source_race_id": source_race_id,
            "name": race.race,
            "race_date": as_date(race.date),
            "race_date_jalali": jalali_string(as_date(race.date)),
            "track": race.track,
            "racecourse_code": race.racecourse_code,
            "province": race.province,
            "distance": race.distance,
            "surface": race.surface,
            "race_number": race.race_number,
            "weather": race.weather,
            "prize_json": race.prize if isinstance(race.prize, dict) else (
                {"value": race.prize} if race.prize is not None else None
            ),
            "payload_json": payload,
        },
    )
    if new_race is None:
        logger.info("Raw race unchanged source_id={} — history preserved", source_race_id)
        return session.scalar(
            select(RawRace).where(*identity, RawRace.is_current.is_(True))
        )

    # Attach entries only to the new race version (old versions keep old entries)
    for horse in race.horses:
        raw_horse: RawHorse | None = None
        if horse.horse_id:
            raw_horse = append_raw_horse(
                session,
                source=source,
                source_horse_id=horse.horse_id,
                name=horse.name,
                sex=horse.sex,
                profile_url=horse.horse_profile_url,
                payload=horse.model_dump(mode="json", by_alias=True),
                source_url=horse.horse_profile_url,
                parser_version=parser_version,
            )
        entry_payload = horse.model_dump(mode="json", by_alias=True)
        entry = RawRaceEntry(
            race_id=new_race.id,
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
            payload_json=entry_payload,
            source_url=race.source_url,
            parser_version=parser_version,
            crawl_time=now_utc(),
            updated_time=now_utc(),
            source_hash=compute_source_hash(entry_payload),
            is_current=True,
            version=1,
        )
        session.add(entry)

    session.flush()
    logger.info(
        "Appended raw race id={} source_id={} version={} entries={}",
        new_race.id,
        new_race.source_race_id,
        new_race.version,
        len(race.horses),
    )
    return new_race


def ingest_horse_history(
    session: Session,
    history: HorseHistory,
    *,
    source: str = "asbdavani",
    parser_version: str = PARSER_VERSION,
) -> RawHorse:
    """Append horse profile version + historical start versions (no overwrite)."""
    profile: HorseProfile = history.horse
    if not profile.horse_id:
        record_parser_error(
            session,
            error_type="missing_horse_id",
            message="Horse history missing horseId",
            source=source,
            source_url=profile.profile_url,
            payload=history.model_dump(mode="json", by_alias=True),
            parser_version=parser_version,
        )
        raise ValueError("Horse history requires horse_id for warehouse ingest")

    horse = append_raw_horse(
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
        source_url=profile.profile_url,
        parser_version=parser_version,
    )

    for row in history.history:
        race_date = as_date(row.race_date)
        payload = row.model_dump(mode="json", by_alias=True)
        prepare_append(
            session,
            model=RawHorseStart,
            identity_filters=[
                RawHorseStart.source == source,
                RawHorseStart.source_horse_id == profile.horse_id,
                RawHorseStart.race_date == race_date,
                RawHorseStart.race_number == row.race_number,
                RawHorseStart.track == row.track,
                RawHorseStart.number == row.number,
            ],
            payload=payload,
            source_url=row.race_url or profile.profile_url,
            parser_version=parser_version,
            field_values={
                "source": source,
                "horse_id": horse.id,
                "source_horse_id": profile.horse_id,
                "race_name": row.race_name,
                "race_date": race_date,
                "track": row.track,
                "race_number": row.race_number,
                "distance": row.distance,
                "surface": row.surface,
                "number": row.number,
                "weight": row.weight,
                "jockey": row.jockey,
                "trainer": row.trainer,
                "owner": row.owner,
                "source_rating": row.rating,
                "barrier": row.barrier,
                "finish_position": row.finish_position,
                "time_raw": str(row.time) if row.time is not None else None,
                "margin": row.margin,
                "odds": row.odds,
                "race_url": row.race_url,
                "payload_json": payload,
            },
        )

    session.flush()
    logger.info(
        "Ingested raw horse history horse_id={} starts_in_payload={}",
        horse.id,
        len(history.history),
    )
    return horse


# Backward-compatible alias used by older call sites / collector persist path
upsert_raw_horse = append_raw_horse
