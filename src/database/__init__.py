"""Database / data-warehouse package."""

from src.database.base import Base
from src.database.features import (
    FeatHorseCareer,
    FeatHorseDistance,
    FeatHorseForm,
    FeatJockeyStats,
    FeatTrainerStats,
    FeaturePipelineRun,
)
from src.database.raw import (
    RawHorse,
    RawHorseStart,
    RawIngestRun,
    RawRace,
    RawRaceEntry,
)
from src.database.repository import (
    finish_ingest_run,
    ingest_horse_history,
    ingest_race,
    start_ingest_run,
    upsert_raw_horse,
)
from src.database.session import get_engine, init_db, reset_engine, session_scope

__all__ = [
    "Base",
    "FeatHorseCareer",
    "FeatHorseDistance",
    "FeatHorseForm",
    "FeatJockeyStats",
    "FeatTrainerStats",
    "FeaturePipelineRun",
    "RawHorse",
    "RawHorseStart",
    "RawIngestRun",
    "RawRace",
    "RawRaceEntry",
    "finish_ingest_run",
    "get_engine",
    "ingest_horse_history",
    "ingest_race",
    "init_db",
    "reset_engine",
    "session_scope",
    "start_ingest_run",
    "upsert_raw_horse",
]
