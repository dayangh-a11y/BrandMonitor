"""Five-Parreh combination engine (Phase 1: selection → combinations → cost).

This package does **not** predict, rank, score, or assign probabilities.
"""

from __future__ import annotations

from src.five_parreh.engine import build_summary, calculate_cost, generate_combinations
from src.five_parreh.errors import FiveParrehValidationError
from src.five_parreh.models import (
    Combination,
    CombinationSummary,
    FiveParrehResult,
    HorsePick,
    RaceSelection,
)

__all__ = [
    "Combination",
    "CombinationSummary",
    "FiveParrehResult",
    "FiveParrehValidationError",
    "HorsePick",
    "RaceSelection",
    "build_summary",
    "calculate_cost",
    "generate_combinations",
]
