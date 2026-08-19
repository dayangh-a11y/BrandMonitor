"""Horse weather / track-condition preference features for ML."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean, pstdev
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.database.features import FeatHorseWeather, FeatHorseWeatherBucket, FeatRaceWeather
from src.pipelines.base import FeaturePipeline
from src.pipelines.registry import register_pipeline
from src.warehouse.models import WhRaceResult
from src.weather.metrics import parse_time_to_seconds


def _bucket_stats(
    finishes: list[int],
    times: list[float],
) -> dict[str, Any]:
    starts = len(finishes)
    wins = sum(1 for f in finishes if f == 1)
    return {
        "starts": starts,
        "wins": wins,
        "win_rate": (wins / starts) if starts else None,
        "avg_finish": mean(finishes) if finishes else None,
        "avg_time_s": mean(times) if times else None,
    }


def _preference_score(bucket_map: dict[str, dict[str, Any]]) -> tuple[float | None, str | None]:
    """
    Preference = max win_rate among buckets with >=1 start, weighted lightly by volume.
    Score in 0..1.
    """
    best_key = None
    best_score = None
    for key, st in bucket_map.items():
        starts = int(st.get("starts") or 0)
        wr = st.get("win_rate")
        if starts <= 0 or wr is None:
            continue
        score = float(wr) * (1.0 - 0.5 / (starts + 0.5))
        if best_score is None or score > best_score:
            best_score = score
            best_key = key
    return (round(best_score, 4) if best_score is not None else None, best_key)


def _sensitivity(bucket_map: dict[str, dict[str, Any]]) -> float | None:
    """Higher when win rates diverge across weather/track buckets."""
    rates = [
        float(st["win_rate"])
        for st in bucket_map.values()
        if st.get("win_rate") is not None and int(st.get("starts") or 0) >= 1
    ]
    if len(rates) < 2:
        return 0.0 if rates else None
    return round(float(pstdev(rates)), 4)


class HorseWeatherPipeline(FeaturePipeline):
    name = "horse_weather"
    version = "1"

    def compute(self, session: Session, *, pipeline_run_id: int) -> int:
        session.execute(delete(FeatHorseWeatherBucket))
        session.execute(delete(FeatHorseWeather))
        session.flush()

        # horse_id -> dimension -> bucket -> finishes / times
        data: dict[int, dict[str, dict[str, dict[str, list]]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(lambda: {"finishes": [], "times": []}))
        )

        q = (
            select(
                WhRaceResult.horse_id,
                WhRaceResult.finish_position,
                WhRaceResult.time_raw,
                FeatRaceWeather.weather_condition,
                FeatRaceWeather.weather_category,
                FeatRaceWeather.track_condition,
                FeatRaceWeather.temp_range,
            )
            .join(FeatRaceWeather, FeatRaceWeather.race_id == WhRaceResult.race_id)
            .where(WhRaceResult.horse_id.is_not(None))
        )
        for horse_id, finish, time_raw, cond, cat, track, t_range in session.execute(q):
            if horse_id is None or finish is None or int(finish) <= 0:
                continue
            hid = int(horse_id)
            fin = int(finish)
            sec = parse_time_to_seconds(time_raw)
            dims = {
                "weather_condition": cond or "unknown",
                "weather_category": cat or "unknown",
                "track_condition": track or "unknown",
                "temp_range": t_range or "unknown",
            }
            for dim, key in dims.items():
                slot = data[hid][dim][str(key)]
                slot["finishes"].append(fin)
                if sec is not None:
                    slot["times"].append(sec)

        now = datetime.now(timezone.utc)
        horse_count = 0
        bucket_count = 0

        for horse_id, dims in data.items():
            weather_map = {
                k: _bucket_stats(v["finishes"], v["times"])
                for k, v in dims.get("weather_condition", {}).items()
            }
            category_map = {
                k: _bucket_stats(v["finishes"], v["times"])
                for k, v in dims.get("weather_category", {}).items()
            }
            track_map = {
                k: _bucket_stats(v["finishes"], v["times"])
                for k, v in dims.get("track_condition", {}).items()
            }
            temp_map = {
                k: _bucket_stats(v["finishes"], v["times"])
                for k, v in dims.get("temp_range", {}).items()
            }
            time_by_weather = {
                k: {
                    "starts": st["starts"],
                    "avg_time_s": st["avg_time_s"],
                    "wins": st["wins"],
                }
                for k, st in weather_map.items()
            }

            track_pref, preferred_track = _preference_score(track_map)
            _, preferred_cat = _preference_score(category_map)
            sensitivity = _sensitivity(category_map) if category_map else _sensitivity(weather_map)

            starts_total = sum(int(st["starts"]) for st in weather_map.values()) or sum(
                int(st["starts"]) for st in track_map.values()
            )

            session.add(
                FeatHorseWeather(
                    horse_id=horse_id,
                    pipeline_run_id=pipeline_run_id,
                    computed_at=now,
                    starts_with_weather=starts_total,
                    weather_sensitivity_score=sensitivity,
                    track_condition_preference_score=track_pref,
                    preferred_track_condition=preferred_track,
                    preferred_weather_category=preferred_cat,
                    win_rate_by_weather_json=weather_map,
                    win_rate_by_track_json=track_map,
                    avg_finish_by_temp_range_json={
                        k: {"starts": st["starts"], "avg_finish": st["avg_finish"]}
                        for k, st in temp_map.items()
                    },
                    avg_time_by_weather_json=time_by_weather,
                    features_json={
                        "win_rate_by_weather_category": category_map,
                    },
                )
            )
            horse_count += 1

            for dimension, buckets in (
                ("weather_condition", weather_map),
                ("weather_category", category_map),
                ("track_condition", track_map),
                ("temp_range", temp_map),
            ):
                for key, st in buckets.items():
                    session.add(
                        FeatHorseWeatherBucket(
                            horse_id=horse_id,
                            dimension=dimension,
                            bucket_key=key,
                            pipeline_run_id=pipeline_run_id,
                            computed_at=now,
                            starts=int(st["starts"]),
                            wins=int(st["wins"]),
                            win_rate=st["win_rate"],
                            avg_finish=st["avg_finish"],
                            avg_time_seconds=st["avg_time_s"],
                        )
                    )
                    bucket_count += 1

        session.flush()
        return horse_count + bucket_count


def register() -> None:
    register_pipeline("horse_weather", HorseWeatherPipeline)
