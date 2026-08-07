"""
Standardization platform — 15 modules for reproducible horse-racing analytics.

Layer separation (Module 15):
  RAW → METRICS → FEATURES → PREDICTIONS → RECOMMENDATIONS
Never mix these layers.
"""

from __future__ import annotations

from src.standardization.constants import PLATFORM_VERSION, MODULES
from src.standardization.orchestrator import run_standardization, StandardizationReport

__all__ = [
    "PLATFORM_VERSION",
    "MODULES",
    "run_standardization",
    "StandardizationReport",
]
