"""
Virtual Race Engine — score hypothetical races without a database race_id.

Builds a temporary field from horse list + card attributes, then reuses
pre-race / market scoring. Does not save unless persist=True.
"""

from __future__ import annotations

from src.virtual_race.engine import build_virtual_race_report
from src.virtual_race.scenario import (
    VirtualHorseEntry,
    VirtualRaceScenario,
    scenario_from_dict,
)

__all__ = [
    "VirtualHorseEntry",
    "VirtualRaceScenario",
    "build_virtual_race_report",
    "scenario_from_dict",
]

PLATFORM_VERSION = "1.0.0"
