"""FastAPI dependencies."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException

from src.api.config import (
    CANONICAL_DATASET_PATH,
    get_api_settings,
    missing_production_dataset_message,
)
from src.prediction_engine.facade import FreezeBackedEngine


@lru_cache(maxsize=1)
def get_engine() -> FreezeBackedEngine:
    settings = get_api_settings()
    engine = FreezeBackedEngine.from_paths(
        settings.prediction_dataset_path,
        settings.prediction_freeze_path,
        verify_freeze=settings.prediction_verify_freeze,
        default_baseline=settings.prediction_default_baseline,
        horse_name_index_path=settings.horse_name_index_path,
    )
    try:
        engine.store.load()
    except Exception as exc:  # noqa: BLE001
        engine.store.load_error = str(exc)
    return engine


def require_engine() -> FreezeBackedEngine:
    engine = get_engine()
    if not engine.store.loaded:
        try:
            engine.store.load()
        except Exception as exc:  # noqa: BLE001
            settings = get_api_settings()
            if settings.is_production_dataset_mode and not Path(
                settings.prediction_dataset_path
            ).exists():
                detail = missing_production_dataset_message(
                    settings.prediction_dataset_path,
                    settings.prediction_freeze_path,
                )
            else:
                detail = (
                    "Prediction dataset unavailable. Restore "
                    f"{CANONICAL_DATASET_PATH} matching freeze metadata. ({exc})"
                )
            raise HTTPException(status_code=503, detail=detail) from None
    return engine


def clear_engine_cache() -> None:
    get_engine.cache_clear()


def parse_positive_int(value: str, *, field: str) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail=f"Invalid {field}: must be an integer") from None
    if n < 0:
        raise HTTPException(status_code=422, detail=f"Invalid {field}: must be >= 0")
    return n
