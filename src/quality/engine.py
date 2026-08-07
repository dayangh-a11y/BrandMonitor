"""Data quality validation pipeline (infrastructure — no analytics stats)."""

from __future__ import annotations

import re
import time
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import urlparse

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.database.raw import RawHorse, RawParserError, RawRace, RawRaceEntry
from src.quality.models import QualityCheckRun, QualityIssue
from src.warehouse.models import (
    WhEntityMatch,
    WhHorse,
    WhJockey,
    WhOwner,
    WhRace,
    WhTrainer,
)

_TIME_RE = re.compile(
    r"^(\d+:)?\d{1,2}\.\d{1,3}$|^(\d+:\d{2}(\.\d+)?)$|^\d+(\.\d+)?$"
)


def _issue(
    session: Session,
    run: QualityCheckRun,
    *,
    check_name: str,
    message: str,
    severity: str = "warning",
    entity_type: str | None = None,
    entity_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        QualityIssue(
            run_id=run.id,
            check_name=check_name,
            severity=severity,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            message=message,
            details_json=details,
        )
    )


def _is_valid_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _count(session: Session, model) -> int:
    return len(list(session.scalars(select(model.id)).all()))


def run_quality_checks(session: Session) -> dict[str, Any]:
    started = time.perf_counter()
    run = QualityCheckRun(status="running")
    session.add(run)
    session.flush()

    missing = 0
    duplicates = 0
    invalid_dates = 0
    invalid_ratings = 0
    invalid_times = 0
    broken_urls = 0

    # Missing values on current raw races
    for race in session.scalars(select(RawRace).where(RawRace.is_current.is_(True))):
        for field in ("name", "race_date", "track", "distance"):
            if getattr(race, field) is None:
                missing += 1
                _issue(
                    session,
                    run,
                    check_name="missing_values",
                    message=f"RawRace missing {field}",
                    entity_type="raw_race",
                    entity_id=race.id,
                    details={"field": field, "source_race_id": race.source_race_id},
                )
        if race.race_date and race.race_date > date.today().replace(year=date.today().year + 2):
            invalid_dates += 1
            _issue(
                session,
                run,
                check_name="invalid_dates",
                message="Race date far in the future",
                severity="error",
                entity_type="raw_race",
                entity_id=race.id,
                details={"race_date": str(race.race_date)},
            )
        if race.source_url and not _is_valid_url(race.source_url):
            broken_urls += 1
            _issue(
                session,
                run,
                check_name="broken_links",
                message="Invalid race source_url",
                severity="error",
                entity_type="raw_race",
                entity_id=race.id,
                details={"source_url": race.source_url},
            )

    for entry in session.scalars(select(RawRaceEntry).where(RawRaceEntry.is_current.is_(True))):
        if not entry.name:
            missing += 1
            _issue(
                session,
                run,
                check_name="missing_values",
                message="Race entry missing name",
                entity_type="raw_race_entry",
                entity_id=entry.id,
            )
        if entry.source_rating is not None and entry.source_rating < 0:
            invalid_ratings += 1
            _issue(
                session,
                run,
                check_name="invalid_ratings",
                message="Negative source rating",
                severity="error",
                entity_type="raw_race_entry",
                entity_id=entry.id,
                details={"source_rating": entry.source_rating},
            )
        if entry.time_raw and not _TIME_RE.match(str(entry.time_raw).strip()):
            invalid_times += 1
            _issue(
                session,
                run,
                check_name="invalid_times",
                message="Unexpected time format",
                entity_type="raw_race_entry",
                entity_id=entry.id,
                details={"time_raw": entry.time_raw},
            )
        if entry.profile_url and not _is_valid_url(entry.profile_url):
            broken_urls += 1
            _issue(
                session,
                run,
                check_name="broken_links",
                message="Invalid horse profile_url",
                severity="error",
                entity_type="raw_race_entry",
                entity_id=entry.id,
                details={"profile_url": entry.profile_url},
            )

    for horse in session.scalars(select(RawHorse).where(RawHorse.is_current.is_(True))):
        if horse.profile_url and not _is_valid_url(horse.profile_url):
            broken_urls += 1
            _issue(
                session,
                run,
                check_name="broken_links",
                message="Invalid horse profile_url",
                severity="error",
                entity_type="raw_horse",
                entity_id=horse.id,
            )
        if horse.birthdate and horse.birthdate > date.today():
            invalid_dates += 1
            _issue(
                session,
                run,
                check_name="invalid_dates",
                message="Horse birthdate in the future",
                severity="error",
                entity_type="raw_horse",
                entity_id=horse.id,
            )

    # Duplicate entity candidates from resolution table
    duplicates = len(
        list(
            session.scalars(
                select(WhEntityMatch.id).where(WhEntityMatch.status == "candidate")
            )
        )
    )
    for match in session.scalars(
        select(WhEntityMatch).where(WhEntityMatch.status == "candidate").limit(500)
    ):
        _issue(
            session,
            run,
            check_name="duplicate_records",
            message=f"Duplicate candidate {match.entity_type}",
            entity_type=match.entity_type,
            entity_id=f"{match.left_key}|{match.right_key}",
            details={"score": match.score, "method": match.method},
        )

    parser_errors = _count(session, RawParserError)
    for err in session.scalars(select(RawParserError).where(RawParserError.resolved.is_(False))):
        _issue(
            session,
            run,
            check_name="unexpected_parser_output",
            message=err.message,
            severity="error",
            entity_type="parser",
            entity_id=err.id,
            details={"error_type": err.error_type, "source_url": err.source_url},
        )

    duration = time.perf_counter() - started
    summary = {
        "races": _count(session, WhRace) or _count(session, RawRace),
        "horses": _count(session, WhHorse) or _count(session, RawHorse),
        "jockeys": _count(session, WhJockey),
        "trainers": _count(session, WhTrainer),
        "owners": _count(session, WhOwner),
        "duplicate_count": duplicates,
        "missing_value_count": missing,
        "invalid_dates": invalid_dates,
        "invalid_ratings": invalid_ratings,
        "invalid_times": invalid_times,
        "parser_errors": parser_errors,
        "broken_urls": broken_urls,
        "processing_speed_seconds": round(duration, 4),
        "rows_per_second": round(
            (
                _count(session, RawRace)
                + _count(session, RawRaceEntry)
                + _count(session, RawHorse)
            )
            / duration
            if duration > 0
            else 0.0,
            2,
        ),
    }
    run.summary_json = summary
    run.status = "success"
    run.finished_at = datetime.now(timezone.utc)
    run.duration_seconds = duration
    session.flush()
    logger.info("Quality check complete {}", summary)
    return summary


def format_quality_report(summary: dict[str, Any]) -> str:
    lines = [
        "=== Data Quality Report ===",
        f"Number of races:      {summary.get('races', 0)}",
        f"Number of horses:     {summary.get('horses', 0)}",
        f"Number of jockeys:    {summary.get('jockeys', 0)}",
        f"Number of trainers:   {summary.get('trainers', 0)}",
        f"Number of owners:     {summary.get('owners', 0)}",
        f"Duplicate count:      {summary.get('duplicate_count', 0)}",
        f"Missing value count:  {summary.get('missing_value_count', 0)}",
        f"Parser errors:        {summary.get('parser_errors', 0)}",
        f"Broken URLs:          {summary.get('broken_urls', 0)}",
        f"Invalid dates:        {summary.get('invalid_dates', 0)}",
        f"Invalid ratings:      {summary.get('invalid_ratings', 0)}",
        f"Invalid times:        {summary.get('invalid_times', 0)}",
        f"Processing speed:     {summary.get('processing_speed_seconds', 0)}s "
        f"({summary.get('rows_per_second', 0)} rows/s)",
    ]
    return "\n".join(lines)
