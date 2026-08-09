"""Warehouse package — normalized curated layer + entity resolution."""

from src.warehouse.entities import run_entity_resolution
from src.warehouse.etl import build_warehouse
from src.warehouse.models import (
    WhEntityMatch,
    WhHorse,
    WhHorsePedigree,
    WhJockey,
    WhOwner,
    WhRace,
    WhRaceResult,
    WhRaceVideo,
    WhRaceWeather,
    WhTrainer,
)

__all__ = [
    "WhEntityMatch",
    "WhHorse",
    "WhHorsePedigree",
    "WhJockey",
    "WhOwner",
    "WhRace",
    "WhRaceResult",
    "WhRaceVideo",
    "WhRaceWeather",
    "WhTrainer",
    "build_warehouse",
    "run_entity_resolution",
]
