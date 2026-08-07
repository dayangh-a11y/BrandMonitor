"""Open-Meteo Archive API client (no API key required)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any

import time

from loguru import logger

from src.utils.retry import FetchError

DEFAULT_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

HOURLY_VARS = (
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "weather_code",
    "cloud_cover",
    "wind_speed_10m",
    "wind_direction_10m",
    "surface_pressure",
    "visibility",
)

DAILY_VARS = (
    "weather_code",
    "temperature_2m_mean",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "precipitation_hours",
    "wind_speed_10m_max",
)


def fetch_archive(
    *,
    latitude: float,
    longitude: float,
    start_date: date,
    end_date: date,
    timezone: str = "Asia/Tehran",
    base_url: str = DEFAULT_ARCHIVE_URL,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    """Fetch historical weather for a lat/lon date range."""
    if end_date < start_date:
        raise ValueError("end_date must be >= start_date")

    params = {
        "latitude": f"{latitude:.5f}",
        "longitude": f"{longitude:.5f}",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "hourly": ",".join(HOURLY_VARS),
        "daily": ",".join(DAILY_VARS),
        "timezone": timezone,
        "wind_speed_unit": "kmh",
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"

    logger.debug(
        "Open-Meteo fetch lat={} lon={} {}..{}",
        latitude,
        longitude,
        start_date,
        end_date,
    )
    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "BrandMonitor-weather/1.0",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                body = resp.read().decode("utf-8", "replace")
            data = json.loads(body)
            if not isinstance(data, dict):
                raise FetchError("Open-Meteo returned non-object JSON")
            return data
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            last_exc = FetchError(f"Open-Meteo HTTP {exc.code}: {detail}")
        except Exception as exc:  # noqa: BLE001
            last_exc = FetchError(str(exc))
        logger.warning("Open-Meteo attempt {}/3 failed: {}", attempt, last_exc)
        time.sleep(1.2 * attempt)
    assert last_exc is not None
    raise last_exc


def daily_precip_map(payload: dict[str, Any]) -> dict[date, float]:
    """Map observation dates → precipitation_sum (mm)."""
    daily = payload.get("daily") or {}
    times = daily.get("time") or []
    precip = daily.get("precipitation_sum") or []
    out: dict[date, float] = {}
    for i, ts in enumerate(times):
        try:
            d = date.fromisoformat(str(ts)[:10])
        except ValueError:
            continue
        val = precip[i] if i < len(precip) else None
        out[d] = float(val) if val is not None else 0.0
    return out


def trailing_precip_sum(
    precip_by_day: dict[date, float],
    *,
    on: date,
    days: int,
) -> float:
    """Sum precipitation over the ``days`` calendar days *before* ``on`` (exclusive)."""
    total = 0.0
    for i in range(1, days + 1):
        total += float(precip_by_day.get(on - timedelta(days=i), 0.0))
    return total
