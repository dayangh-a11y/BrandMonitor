"""Pipeline registry."""

from __future__ import annotations

from collections.abc import Callable

from src.pipelines.base import FeaturePipeline
from src.utils.retry import CollectorError

_REGISTRY: dict[str, Callable[[], FeaturePipeline]] = {}


def register_pipeline(name: str, factory: Callable[[], FeaturePipeline]) -> None:
    _REGISTRY[name.strip().lower()] = factory


def get_pipeline(name: str) -> FeaturePipeline:
    _ensure_builtins()
    key = name.strip().lower()
    if key not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise CollectorError(f"Unknown pipeline '{name}'. Available: {available}")
    return _REGISTRY[key]()


def list_pipelines() -> list[str]:
    _ensure_builtins()
    return sorted(_REGISTRY)


def _ensure_builtins() -> None:
    if _REGISTRY:
        return
    from src.pipelines import (
        horse_career,
        horse_distance,
        horse_form,
        horse_weather,
        people_stats,
        race_weather,
    )

    horse_career.register()
    horse_form.register()
    horse_distance.register()
    people_stats.register()
    race_weather.register()
    horse_weather.register()
