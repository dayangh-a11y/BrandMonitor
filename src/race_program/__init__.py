"""Future race-program domain (meetings + races + Five-Parreh designations).

This module is the single source for upcoming-race discovery used by
``/predict`` and ``/fiveparreh``. It does NOT score, rank, or generate
Five-Parreh combinations.
"""

from src.race_program.eligibility import (
    DEFAULT_UPCOMING_DAYS,
    is_eligible_for_prediction,
    utc_now,
)
from src.race_program.models import FiveParrehProgramEvent, Meeting, ProgramRace
from src.race_program.service import RaceProgramService, load_race_program

__all__ = [
    "DEFAULT_UPCOMING_DAYS",
    "FiveParrehProgramEvent",
    "Meeting",
    "ProgramRace",
    "RaceProgramService",
    "is_eligible_for_prediction",
    "load_race_program",
    "utc_now",
]
