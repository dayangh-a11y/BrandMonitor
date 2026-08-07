"""Weather metrics + schema smoke tests (no live API required)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from src.database.base import Base
from src.database.features import FeatHorseWeather, FeatHorseWeatherBucket, FeatRaceWeather
from src.database.raw import RawWeatherObservation
from src.pipelines.horse_weather import HorseWeatherPipeline
from src.pipelines.race_weather import RaceWeatherPipeline
from src.racecourses import get_racecourse
from src.utils.settings import Settings
from src.warehouse.models import WhHorse, WhRace, WhRaceResult, WhRaceWeather
from src.weather.etl import attach_weather_to_warehouse
from src.weather.metrics import (
    estimate_track_condition,
    heat_index_celsius,
    observation_snapshot,
    surface_moisture_indicator,
    temperature_range,
    weather_category,
    wmo_to_condition,
)


def test_racecourses_have_coordinates() -> None:
    for code in ("gonbad-kavous", "aq-qala", "bandar-torkaman"):
        course = get_racecourse(code)
        assert course is not None
        assert course.latitude is not None
        assert course.longitude is not None


def test_wmo_and_category_helpers() -> None:
    assert wmo_to_condition(0) == "clear"
    assert wmo_to_condition(63) == "rain"
    assert weather_category("clear") == "clear"
    assert weather_category("rain") == "precip"
    assert weather_category("thunderstorm") == "storm"
    assert temperature_range(5) == "cold"
    assert temperature_range(30) == "warm"


def test_heat_index_and_moisture() -> None:
    assert heat_index_celsius(20, 50) == 20  # below HI applicability → dry bulb
    hi = heat_index_celsius(35, 70)
    assert hi is not None and hi > 35
    assert 0 <= surface_moisture_indicator(
        precip_race_day_mm=0, precip_prev_3d_mm=0, precip_prev_7d_mm=0
    ) <= 0.05
    wet = surface_moisture_indicator(
        precip_race_day_mm=8, precip_prev_3d_mm=20, precip_prev_7d_mm=40
    )
    assert wet > 0.7
    assert estimate_track_condition(
        precip_race_day_mm=0, precip_prev_3d_mm=0, precip_prev_7d_mm=0
    ) == "dry"
    assert estimate_track_condition(
        precip_race_day_mm=6, precip_prev_3d_mm=30, precip_prev_7d_mm=40
    ) == "muddy"


def test_observation_snapshot_picks_hour() -> None:
    payload = {
        "hourly": {
            "time": [
                "2026-02-14T12:00",
                "2026-02-14T14:00",
                "2026-02-14T16:00",
            ],
            "temperature_2m": [10.0, 18.5, 17.0],
            "relative_humidity_2m": [40, 55, 60],
            "precipitation": [0.0, 0.2, 0.0],
            "weather_code": [1, 61, 2],
            "cloud_cover": [10, 80, 40],
            "wind_speed_10m": [5, 12, 8],
            "wind_direction_10m": [180, 200, 210],
            "surface_pressure": [1012, 1011, 1010],
            "visibility": [10000, 8000, 9000],
        },
        "daily": {"precipitation_sum": [1.5], "time": ["2026-02-14"]},
    }
    snap = observation_snapshot(payload, hour=14)
    assert snap["air_temperature_c"] == 18.5
    assert snap["weather_condition"] == "rain"
    assert snap["weather_category"] == "precip"
    assert snap["heat_index_c"] is not None


@pytest.fixture()
def mem_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    # Import model modules so metadata is complete
    import src.database.features  # noqa: F401
    import src.database.raw  # noqa: F401
    import src.features.models  # noqa: F401
    import src.quality.models  # noqa: F401
    import src.crawler.models  # noqa: F401
    import src.crawler.stats  # noqa: F401
    import src.warehouse.models  # noqa: F401

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    finally:
        session.close()
        engine.dispose()


def _sample_day_payload(*, temp: float = 18.0, precip: float = 0.0, code: int = 1) -> dict:
    hours = list(range(24))
    return {
        "latitude": 37.25,
        "longitude": 55.17,
        "timezone": "Asia/Tehran",
        "hourly": {
            "time": [f"2026-02-14T{h:02d}:00" for h in hours],
            "temperature_2m": [temp] * 24,
            "relative_humidity_2m": [50] * 24,
            "precipitation": [precip if h == 14 else 0.0 for h in hours],
            "weather_code": [code] * 24,
            "cloud_cover": [40] * 24,
            "wind_speed_10m": [10] * 24,
            "wind_direction_10m": [180] * 24,
            "surface_pressure": [1013] * 24,
            "visibility": [10000] * 24,
        },
        "daily": {
            "time": ["2026-02-14"],
            "precipitation_sum": [precip],
            "temperature_2m_mean": [temp],
            "weather_code": [code],
        },
        "observation_date": "2026-02-14",
    }


def test_attach_and_feature_pipelines(mem_session: Session) -> None:
    from datetime import timedelta

    race_day = date(2026, 2, 14)
    # lookback days for trailing features
    for offset, precip in (
        (0, 0.0),
        (1, 1.0),
        (2, 2.0),
        (3, 0.5),
        (4, 0.0),
        (5, 0.0),
        (6, 0.0),
        (7, 3.0),
    ):
        d = race_day - timedelta(days=offset)
        payload = _sample_day_payload(temp=16 + offset * 0.2, precip=precip, code=1 if precip == 0 else 61)
        payload["hourly"]["time"] = [f"{d.isoformat()}T{h:02d}:00" for h in range(24)]
        payload["daily"]["time"] = [d.isoformat()]
        payload["observation_date"] = d.isoformat()
        mem_session.add(
            RawWeatherObservation(
                source="open-meteo",
                racecourse_code="gonbad-kavous",
                observation_date=d,
                latitude=37.25,
                longitude=55.17,
                timezone="Asia/Tehran",
                temp_mean_c=16 + offset * 0.2,
                precip_sum_mm=precip,
                weather_code=1 if precip == 0 else 61,
                payload_json=payload,
                source_url="test",
                parser_version="1.0.0",
                source_hash=f"hash-{offset}",
                is_current=True,
                version=1,
                crawl_time=datetime.now(timezone.utc),
                updated_time=datetime.now(timezone.utc),
            )
        )

    race = WhRace(
        source="asbdavani",
        source_race_id="r1",
        name="test",
        race_date=race_day,
        track="گنبدکاووس",
        racecourse_code="gonbad-kavous",
        distance=1600,
        surface="تروبرد",
        race_number=1,
    )
    mem_session.add(race)
    mem_session.flush()

    horse = WhHorse(source="asbdavani", source_horse_id="h1", name="Test Horse")
    mem_session.add(horse)
    mem_session.flush()
    mem_session.add(
        WhRaceResult(
            race_id=race.id,
            horse_id=horse.id,
            number=1,
            finish_position=1,
            time_raw="1:40.000",
            source_rating=80,
        )
    )
    mem_session.flush()

    settings = Settings(
        database_url="sqlite:///:memory:",
        weather_default_race_hour=14,
        weather_lookback_days=7,
    )
    stats = attach_weather_to_warehouse(mem_session, settings=settings)
    assert stats["upserted"] == 1
    wx = mem_session.scalar(select(WhRaceWeather).where(WhRaceWeather.race_id == race.id))
    assert wx is not None
    assert wx.air_temperature_c is not None
    assert wx.track_condition in {"dry", "firm", "soft", "wet", "muddy"}
    assert wx.start_time_estimated is True
    assert wx.weather_condition is not None

    race_rows = RaceWeatherPipeline().run(mem_session).rows_upserted
    assert race_rows == 1
    feat = mem_session.scalar(select(FeatRaceWeather).where(FeatRaceWeather.race_id == race.id))
    assert feat is not None
    assert feat.weather_category is not None
    assert feat.surface_moisture is not None
    assert feat.rainfall_prev_3d_mm is not None
    assert feat.rainfall_prev_7d_mm is not None

    horse_rows = HorseWeatherPipeline().run(mem_session).rows_upserted
    assert horse_rows >= 1
    hw = mem_session.get(FeatHorseWeather, horse.id)
    assert hw is not None
    assert hw.starts_with_weather >= 1
    assert hw.win_rate_by_weather_json
    buckets = mem_session.scalars(
        select(FeatHorseWeatherBucket).where(FeatHorseWeatherBucket.horse_id == horse.id)
    ).all()
    assert buckets
