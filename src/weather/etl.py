"""Attach structured weather snapshots to warehouse races."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.raw import RawWeatherObservation
from src.utils.settings import Settings, get_settings
from src.warehouse.models import WhRace, WhRaceWeather
from src.weather.metrics import (
    estimate_track_condition,
    observation_snapshot,
    safe_mean,
)
from src.weather.open_meteo import daily_precip_map, trailing_precip_sum


def _as_date(value: date | datetime | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _load_obs_index(
    session: Session,
) -> dict[tuple[str, date], RawWeatherObservation]:
    rows = session.scalars(
        select(RawWeatherObservation).where(RawWeatherObservation.is_current.is_(True))
    ).all()
    out: dict[tuple[str, date], RawWeatherObservation] = {}
    for row in rows:
        d = _as_date(row.observation_date)
        if d is None:
            continue
        out[(row.racecourse_code, d)] = row
    return out


def attach_weather_to_warehouse(
    session: Session,
    *,
    settings: Settings | None = None,
) -> dict[str, int]:
    """
    Upsert ``wh_race_weather`` for every warehouse race that has a current
    Raw weather observation on race day.
    """
    cfg = settings or get_settings()
    hour = int(cfg.weather_default_race_hour)
    obs_index = _load_obs_index(session)
    races = session.scalars(select(WhRace).where(WhRace.race_date.is_not(None))).all()

    upserted = 0
    missing = 0

    for race in races:
        race_day = _as_date(race.race_date)
        if race_day is None or not race.racecourse_code:
            missing += 1
            continue
        obs = obs_index.get((race.racecourse_code, race_day))
        if obs is None or not obs.payload_json:
            missing += 1
            continue

        payload = obs.payload_json if isinstance(obs.payload_json, dict) else {}
        snap = observation_snapshot(payload, hour=hour)

        # Trailing precip from neighboring raw days when available
        precip_by_day: dict[date, float] = {}
        for delta in range(0, 8):
            d = race_day - timedelta(days=delta)
            o = obs_index.get((race.racecourse_code, d))
            if o is None:
                continue
            if o.precip_sum_mm is not None:
                precip_by_day[d] = float(o.precip_sum_mm)
            elif o.payload_json:
                precip_by_day.update(daily_precip_map(o.payload_json))

        precip_day = precip_by_day.get(
            race_day,
            float(snap.get("rainfall_day_mm") or snap.get("rainfall_mm") or 0.0),
        )
        precip_3d = trailing_precip_sum(precip_by_day, on=race_day, days=3)
        precip_7d = trailing_precip_sum(precip_by_day, on=race_day, days=7)

        track_condition = estimate_track_condition(
            precip_race_day_mm=precip_day,
            precip_prev_3d_mm=precip_3d,
            precip_prev_7d_mm=precip_7d,
        )

        tz_name = obs.timezone or "Asia/Tehran"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:  # noqa: BLE001
            tz = timezone.utc
        start_local = datetime(
            race_day.year,
            race_day.month,
            race_day.day,
            hour,
            0,
            0,
            tzinfo=tz,
        )

        row = session.scalar(select(WhRaceWeather).where(WhRaceWeather.race_id == race.id))
        if row is None:
            row = WhRaceWeather(race_id=race.id)
            session.add(row)

        row.racecourse_code = race.racecourse_code
        row.observation_date = race_day
        row.air_temperature_c = _f(snap.get("air_temperature_c"))
        row.humidity_pct = _f(snap.get("humidity_pct"))
        row.wind_speed_kmh = _f(snap.get("wind_speed_kmh"))
        row.wind_direction_deg = _f(snap.get("wind_direction_deg"))
        row.wind_direction_compass = snap.get("wind_direction_compass")
        row.pressure_hpa = _f(snap.get("pressure_hpa"))
        row.rainfall_mm = _f(snap.get("rainfall_mm"))
        row.rainfall_day_mm = float(precip_day)
        row.rain_probability_pct = _f(snap.get("rain_probability_pct"))
        row.cloud_cover_pct = _f(snap.get("cloud_cover_pct"))
        row.visibility_m = _f(snap.get("visibility_m"))
        row.weather_condition = snap.get("weather_condition")
        row.weather_code = snap.get("weather_code")
        row.race_start_time = start_local.astimezone(timezone.utc)
        row.start_time_estimated = True
        row.track_condition = track_condition
        row.track_condition_source = "estimated"
        row.raw_weather_id = obs.id
        row.provider = "open-meteo"
        row.updated_at = datetime.now(timezone.utc)
        upserted += 1

    session.flush()
    stats = {"upserted": upserted, "missing_obs": missing, "obs_days": len(obs_index)}
    logger.info("Warehouse race weather attach {}", stats)
    return stats


def _f(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def mean_temp_prev_days(
    obs_index: dict[tuple[str, date], RawWeatherObservation],
    *,
    code: str,
    on: date,
    days: int,
) -> float | None:
    vals: list[float] = []
    for i in range(1, days + 1):
        o = obs_index.get((code, on - timedelta(days=i)))
        if o is None:
            continue
        if o.temp_mean_c is not None:
            vals.append(float(o.temp_mean_c))
    return safe_mean(vals)
