"""Prediction Foundation — leakage-safe pre-race feature engineering.

Rules:
- Observation unit = ONE HORSE × ONE RACE
- Features use ONLY information available BEFORE the race
- Targets are separate and never used in feature calculation
- No ML training in this phase
- No DB mutation; outputs are files under data/ / artifacts
"""

from __future__ import annotations

PLATFORM_VERSION = "0.1.0"

from src.prediction_foundation.baseline_eval import run_baseline_evaluation
from src.prediction_foundation.build import build_prediction_foundation
from src.prediction_foundation.dictionary import FEATURE_DICTIONARY
from src.prediction_foundation.freeze import freeze_dataset, load_freeze
from src.prediction_foundation.leakage import run_leakage_audit
from src.prediction_foundation.readiness import assess_readiness

__all__ = [
    "FEATURE_DICTIONARY",
    "PLATFORM_VERSION",
    "assess_readiness",
    "build_prediction_foundation",
    "freeze_dataset",
    "load_freeze",
    "run_baseline_evaluation",
    "run_leakage_audit",
]
