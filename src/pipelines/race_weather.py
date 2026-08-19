"""Race-level derived weather features (warehouse weather → feat_race_weather)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.database.features import FeatRaceWeather
from src.database.raw import RawWeatherObservation
from src.pipelines.base import FeaturePipeline
from src.pipelines.registry import register_pipeline
from src.warehouse.models import WhRace, WhRaceWeather
from src.weather.metrics import (
    heat_index_celsius,
    surface_moisture_indicator,
    temperature_range,
    weather_category,
)
from src.weather.open_meteo import trailing_precip_sum


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


class RaceWeatherPipeline(FeaturePipeline):
    """
    Builds ML-ready race weather features.

    Reads warehouse race weather + raw daily observations for trailing windows.
    (Weather facts are external extracts, not asbdavani Raw race fields.)
    """

    name = "race_weather"
    version = "1"

    def compute(self, session: Session, *, pipeline_run_id: int) -> int:
        session.execute(delete(FeatRaceWeather))
        session.flush()

        obs_rows = session.scalars(
            select(RawWeatherObservation).where(RawWeatherObservation.is_current.is_(True))
        ).all()
        precip: dict[tuple[str, date], float] = {}
        temps: dict[tuple[str, date], float] = {}
        for o in obs_rows:
            d = _as_date(o.observation_date)
            if d is None:
                continue
            key = (o.racecourse_code, d)
            if o.precip_sum_mm is not None:
                precip[key] = float(o.precip_sum_mm)
            if o.temp_mean_c is not None:
                temps[key] = float(o.temp_mean_c)

        rows = session.execute(
            select(WhRace, WhRaceWeather)
            .join(WhRaceWeather, WhRaceWeather.race_id == WhRace.id)
        ).all()

        count = 0
        now = datetime.now(timezone.utc)
        for race, wx in rows:
            race_day = _as_date(race.race_date) or _as_date(wx.observation_date)
            code = race.racecourse_code or wx.racecourse_code
            if race_day is None or not code:
                continue

            precip_map = {
                d: v for (c, d), v in precip.items() if c == code
            }
            rainfall_3d = trailing_precip_sum(precip_map, on=race_day, days=3)
            rainfall_7d = trailing_precip_sum(precip_map, on=race_day, days=7)

            temp_vals = [
                temps[(code, race_day - timedelta(days=i))]
                for i in range(1, 4)
                if (code, race_day - timedelta(days=i)) in temps
            ]
            avg_temp_3d = sum(temp_vals) / len(temp_vals) if temp_vals else None

            hi = heat_index_celsius(wx.air_temperature_c, wx.humidity_pct)
            cat = weather_category(
                wx.weather_condition,
                precip_mm=wx.rainfall_day_mm or wx.rainfall_mm,
            )
            moisture = surface_moisture_indicator(
                precip_race_day_mm=wx.rainfall_day_mm or wx.rainfall_mm,
                precip_prev_3d_mm=rainfall_3d,
                precip_prev_7d_mm=rainfall_7d,
            )
            t_range = temperature_range(wx.air_temperature_c)

            session.add(
                FeatRaceWeather(
                    race_id=race.id,
                    pipeline_run_id=pipeline_run_id,
                    computed_at=now,
                    avg_temp_prev_3d_c=avg_temp_3d,
                    rainfall_prev_3d_mm=rainfall_3d,
                    rainfall_prev_7d_mm=rainfall_7d,
                    heat_index_c=hi,
                    weather_category=cat,
                    surface_moisture=moisture,
                    temp_range=t_range,
                    air_temperature_c=wx.air_temperature_c,
                    humidity_pct=wx.humidity_pct,
                    wind_speed_kmh=wx.wind_speed_kmh,
                    rainfall_mm=wx.rainfall_mm,
                    track_condition=wx.track_condition,
                    weather_condition=wx.weather_condition,
                    features_json={
                        "pressure_hpa": wx.pressure_hpa,
                        "cloud_cover_pct": wx.cloud_cover_pct,
                        "visibility_m": wx.visibility_m,
                        "wind_direction_compass": wx.wind_direction_compass,
                        "rain_probability_pct": wx.rain_probability_pct,
                        "start_time_estimated": wx.start_time_estimated,
                        "track_condition_source": wx.track_condition_source,
                    },
                )
            )
            count += 1

        session.flush()
        return count


def register() -> None:
    register_pipeline("race_weather", RaceWeatherPipeline)
