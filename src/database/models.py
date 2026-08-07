"""Warehouse model exports (Raw + Features)."""

from __future__ import annotations

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

# Import feature/raw modules so Base.metadata knows all tables
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
]
