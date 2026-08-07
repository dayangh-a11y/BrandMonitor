"""Backfill historical weather observations into Raw (append-only)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.raw import RawWeatherObservation
from src.racecourses import get_racecourse
from src.utils.settings import Settings, get_settings
from src.versioning.policy import prepare_append
from src.warehouse.models import WhRace
from src.weather.open_meteo import fetch_archive


def _daily_slice(payload: dict[str, Any], day: date) -> dict[str, Any]:
    """Build a single-day payload (hourly + daily) from a multi-day archive response."""
    day_s = day.isoformat()
    hourly = payload.get("hourly") or {}
    h_times = hourly.get("time") or []
    keep_idx = [i for i, t in enumerate(h_times) if str(t).startswith(day_s)]
    hourly_out: dict[str, Any] = {}
    for key, arr in hourly.items():
        if not isinstance(arr, list):
            hourly_out[key] = arr
            continue
        hourly_out[key] = [arr[i] for i in keep_idx if i < len(arr)]

    daily = payload.get("daily") or {}
    d_times = daily.get("time") or []
    daily_out: dict[str, Any] = {}
    di = next((i for i, t in enumerate(d_times) if str(t)[:10] == day_s), None)
    for key, arr in daily.items():
        if key == "time":
            daily_out[key] = [day_s]
            continue
        if isinstance(arr, list) and di is not None and di < len(arr):
            daily_out[key] = [arr[di]]
        elif isinstance(arr, list):
            daily_out[key] = []
        else:
            daily_out[key] = arr

    return {
        "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"),
        "timezone": payload.get("timezone"),
        "elevation": payload.get("elevation"),
        "hourly_units": payload.get("hourly_units"),
        "daily_units": payload.get("daily_units"),
        "hourly": hourly_out,
        "daily": daily_out,
        "observation_date": day_s,
    }


def _extract_daily_fields(day_payload: dict[str, Any]) -> dict[str, Any]:
    daily = day_payload.get("daily") or {}

    def _first(key: str) -> Any:
        arr = daily.get(key) or []
        return arr[0] if arr else None

    code = _first("weather_code")
    return {
        "temp_mean_c": _first("temperature_2m_mean"),
        "temp_max_c": _first("temperature_2m_max"),
        "temp_min_c": _first("temperature_2m_min"),
        "precip_sum_mm": _first("precipitation_sum"),
        "weather_code": int(code) if code is not None else None,
    }


def backfill_race_weather(
    session: Session,
    *,
    settings: Settings | None = None,
    racecourse_codes: set[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, int]:
    """
    Fetch Open-Meteo archive weather for race dates (+ lookback window) and
    append RawWeatherObservation rows.
    """
    cfg = settings or get_settings()
    lookback = int(cfg.weather_lookback_days)

    q = select(WhRace.racecourse_code, WhRace.race_date).where(
        WhRace.race_date.is_not(None),
        WhRace.racecourse_code.is_not(None),
    )
    if racecourse_codes:
        q = q.where(WhRace.racecourse_code.in_(sorted(racecourse_codes)))
    if date_from:
        q = q.where(WhRace.race_date >= date_from)
    if date_to:
        q = q.where(WhRace.race_date <= date_to)

    by_course: dict[str, set[date]] = defaultdict(set)
    for code, race_date in session.execute(q):
        if not code or race_date is None:
            continue
        d = race_date if isinstance(race_date, date) else date.fromisoformat(str(race_date)[:10])
        for i in range(0, lookback + 1):
            by_course[str(code)].add(d - timedelta(days=i))

    inserted = 0
    skipped = 0
    failed = 0
    fetched_chunks = 0

    for code, days in sorted(by_course.items()):
        course = get_racecourse(code)
        if course is None or course.latitude is None or course.longitude is None:
            logger.warning("No coordinates for racecourse {}; skip weather", code)
            failed += len(days)
            continue

        ordered = sorted(days)
        # Chunk by contiguous ranges to limit API calls
        chunk_start = ordered[0]
        prev = ordered[0]
        ranges: list[tuple[date, date]] = []
        for d in ordered[1:]:
            if (d - prev).days > 1:
                ranges.append((chunk_start, prev))
                chunk_start = d
            prev = d
        ranges.append((chunk_start, prev))

        for start, end in ranges:
            # Expand start by 0 already included; fetch inclusive
            try:
                payload = fetch_archive(
                    latitude=float(course.latitude),
                    longitude=float(course.longitude),
                    start_date=start,
                    end_date=end,
                    timezone=course.timezone or "Asia/Tehran",
                    base_url=cfg.weather_archive_url,
                )
                fetched_chunks += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception("Weather fetch failed {} {}..{}: {}", code, start, end, exc)
                failed += (end - start).days + 1
                continue

            cursor = start
            while cursor <= end:
                day_payload = _daily_slice(payload, cursor)
                fields = _extract_daily_fields(day_payload)
                source_url = (
                    f"{cfg.weather_archive_url}"
                    f"?latitude={course.latitude}&longitude={course.longitude}"
                    f"&start_date={cursor.isoformat()}&end_date={cursor.isoformat()}"
                )
                row = prepare_append(
                    session,
                    model=RawWeatherObservation,
                    identity_filters=[
                        RawWeatherObservation.source == "open-meteo",
                        RawWeatherObservation.racecourse_code == code,
                        RawWeatherObservation.observation_date == cursor,
                    ],
                    payload=day_payload,
                    source_url=source_url,
                    parser_version=cfg.weather_parser_version,
                    field_values={
                        "source": "open-meteo",
                        "racecourse_code": code,
                        "observation_date": cursor,
                        "latitude": float(course.latitude),
                        "longitude": float(course.longitude),
                        "timezone": course.timezone,
                        "temp_mean_c": fields["temp_mean_c"],
                        "temp_max_c": fields["temp_max_c"],
                        "temp_min_c": fields["temp_min_c"],
                        "precip_sum_mm": fields["precip_sum_mm"],
                        "weather_code": fields["weather_code"],
                        "payload_json": day_payload,
                    },
                )
                if row is None:
                    skipped += 1
                else:
                    inserted += 1
                cursor += timedelta(days=1)

    stats = {
        "courses": len(by_course),
        "chunks_fetched": fetched_chunks,
        "inserted": inserted,
        "skipped_unchanged": skipped,
        "failed": failed,
    }
    logger.info("Weather backfill done {}", stats)
    return stats
