"""Pure weather metric helpers (no I/O) — heat index, categories, track going."""

from __future__ import annotations

import math
from typing import Any

# WMO Weather interpretation codes → coarse labels
# https://open-meteo.com/en/docs
WMO_WEATHER_LABELS: dict[int, str] = {
    0: "clear",
    1: "mainly_clear",
    2: "partly_cloudy",
    3: "overcast",
    45: "fog",
    48: "fog",
    51: "drizzle",
    53: "drizzle",
    55: "drizzle",
    56: "freezing_drizzle",
    57: "freezing_drizzle",
    61: "rain",
    63: "rain",
    65: "rain",
    66: "freezing_rain",
    67: "freezing_rain",
    71: "snow",
    73: "snow",
    75: "snow",
    77: "snow",
    80: "rain_showers",
    81: "rain_showers",
    82: "rain_showers",
    85: "snow_showers",
    86: "snow_showers",
    95: "thunderstorm",
    96: "thunderstorm",
    99: "thunderstorm",
}

WEATHER_CATEGORIES = (
    "clear",
    "cloudy",
    "precip",
    "storm",
    "fog",
    "snow",
    "unknown",
)

TRACK_CONDITIONS = (
    "dry",
    "firm",
    "soft",
    "wet",
    "muddy",
    "unknown",
)

TEMP_RANGES = (
    "cold",      # < 10°C
    "cool",      # 10–18
    "mild",      # 18–25
    "warm",      # 25–32
    "hot",       # >= 32
)


def wmo_to_condition(code: int | None) -> str | None:
    if code is None:
        return None
    try:
        return WMO_WEATHER_LABELS.get(int(code), f"code_{int(code)}")
    except (TypeError, ValueError):
        return None


def weather_category(condition: str | None, *, precip_mm: float | None = None) -> str:
    """Coarse ML-friendly weather bucket."""
    if not condition:
        if precip_mm is not None and precip_mm > 0.2:
            return "precip"
        return "unknown"
    c = condition.lower()
    if c in {"clear", "mainly_clear"}:
        return "clear"
    if c in {"partly_cloudy", "overcast"}:
        return "cloudy"
    if "thunder" in c or c == "thunderstorm":
        return "storm"
    if "fog" in c:
        return "fog"
    if "snow" in c:
        return "snow"
    if any(x in c for x in ("rain", "drizzle", "shower")):
        return "precip"
    if precip_mm is not None and precip_mm > 0.2:
        return "precip"
    return "unknown"


def heat_index_celsius(temp_c: float | None, humidity_pct: float | None) -> float | None:
    """
    NOAA heat index (°C), computed via Rothfusz regression on °F then converted back.

    Valid primarily for T >= ~27°C and RH >= 40%; returns dry-bulb when outside
    the applicable range (still useful as a continuous feature).
    """
    if temp_c is None or humidity_pct is None:
        return None
    t_f = temp_c * 9.0 / 5.0 + 32.0
    rh = max(0.0, min(100.0, float(humidity_pct)))
    if t_f < 80.0:
        return round(temp_c, 3)
    # Rothfusz regression
    hi = (
        -42.379
        + 2.04901523 * t_f
        + 10.14333127 * rh
        - 0.22475541 * t_f * rh
        - 6.83783e-3 * t_f**2
        - 5.481717e-2 * rh**2
        + 1.22874e-3 * t_f**2 * rh
        + 8.5282e-4 * t_f * rh**2
        - 1.99e-6 * t_f**2 * rh**2
    )
    return round((hi - 32.0) * 5.0 / 9.0, 3)


def estimate_track_condition(
    *,
    precip_race_day_mm: float | None,
    precip_prev_3d_mm: float | None,
    precip_prev_7d_mm: float | None = None,
) -> str:
    """
    Estimate going when the source site does not publish track condition.

    Thresholds are deterministic rules for ML reproducibility — not official
    stewards' reports.
    """
    day = float(precip_race_day_mm or 0.0)
    d3 = float(precip_prev_3d_mm or 0.0)
    d7 = float(precip_prev_7d_mm or 0.0)
    if day >= 5.0 or d3 >= 25.0:
        return "muddy"
    if day >= 2.0 or d3 >= 12.0:
        return "wet"
    if d3 >= 4.0 or d7 >= 15.0:
        return "soft"
    if d3 >= 1.0 or day >= 0.2:
        return "firm"
    return "dry"


def surface_moisture_indicator(
    *,
    precip_race_day_mm: float | None,
    precip_prev_3d_mm: float | None,
    precip_prev_7d_mm: float | None,
) -> float:
    """
    Continuous 0..1 moisture proxy for ML models.

    Combines same-day and trailing rainfall with saturating transforms.
    """
    day = max(0.0, float(precip_race_day_mm or 0.0))
    d3 = max(0.0, float(precip_prev_3d_mm or 0.0))
    d7 = max(0.0, float(precip_prev_7d_mm or 0.0))
    # Soft saturations: 10mm day / 30mm 3d / 50mm 7d ≈ "very wet"
    score = (
        0.45 * (1.0 - math.exp(-day / 4.0))
        + 0.35 * (1.0 - math.exp(-d3 / 12.0))
        + 0.20 * (1.0 - math.exp(-d7 / 25.0))
    )
    return round(min(1.0, max(0.0, score)), 4)


def temperature_range(temp_c: float | None) -> str:
    if temp_c is None:
        return "unknown"
    t = float(temp_c)
    if t < 10:
        return "cold"
    if t < 18:
        return "cool"
    if t < 25:
        return "mild"
    if t < 32:
        return "warm"
    return "hot"


def wind_direction_compass(degrees: float | None) -> str | None:
    if degrees is None:
        return None
    try:
        d = float(degrees) % 360.0
    except (TypeError, ValueError):
        return None
    dirs = (
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    )
    idx = int((d + 11.25) // 22.5) % 16
    return dirs[idx]


def safe_mean(values: list[float]) -> float | None:
    nums = [float(v) for v in values if v is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


def parse_time_to_seconds(raw: str | None) -> float | None:
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        if ":" in text:
            parts = text.split(":")
            if len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        return float(text)
    except ValueError:
        return None


def observation_snapshot(payload: dict[str, Any], *, hour: int) -> dict[str, Any]:
    """Pick the hourly slice closest to ``hour`` from an Open-Meteo archive payload."""
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        return {}
    best_i = 0
    best_dist = 99
    for i, ts in enumerate(times):
        try:
            h = int(str(ts)[11:13])
        except (TypeError, ValueError):
            continue
        dist = abs(h - hour)
        if dist < best_dist:
            best_dist = dist
            best_i = i

    def _at(key: str) -> Any:
        arr = hourly.get(key) or []
        if best_i < len(arr):
            return arr[best_i]
        return None

    daily = payload.get("daily") or {}
    precip_day = None
    if daily.get("precipitation_sum"):
        precip_day = daily["precipitation_sum"][0] if daily["precipitation_sum"] else None

    code = _at("weather_code")
    temp = _at("temperature_2m")
    humidity = _at("relative_humidity_2m")
    wind_speed = _at("wind_speed_10m")
    wind_dir = _at("wind_direction_10m")
    pressure = _at("surface_pressure")
    precip = _at("precipitation")
    cloud = _at("cloud_cover")
    visibility = _at("visibility")
    # Archive rarely has precip probability; use binary proxy when missing.
    rain_prob = _at("precipitation_probability")
    if rain_prob is None and precip is not None:
        rain_prob = 100.0 if float(precip) > 0 else 0.0

    condition = wmo_to_condition(int(code) if code is not None else None)
    return {
        "hour_index": best_i,
        "observation_time": times[best_i] if best_i < len(times) else None,
        "air_temperature_c": temp,
        "humidity_pct": humidity,
        "wind_speed_kmh": wind_speed,
        "wind_direction_deg": wind_dir,
        "wind_direction_compass": wind_direction_compass(
            float(wind_dir) if wind_dir is not None else None
        ),
        "pressure_hpa": pressure,
        "rainfall_mm": precip if precip is not None else precip_day,
        "rainfall_day_mm": precip_day,
        "rain_probability_pct": rain_prob,
        "cloud_cover_pct": cloud,
        "visibility_m": visibility,
        "weather_code": int(code) if code is not None else None,
        "weather_condition": condition,
        "weather_category": weather_category(
            condition,
            precip_mm=float(precip) if precip is not None else precip_day,
        ),
        "heat_index_c": heat_index_celsius(
            float(temp) if temp is not None else None,
            float(humidity) if humidity is not None else None,
        ),
    }
