"""Freeze-backed prediction façade.

Thin read-only adapter over ``prediction_foundation.baseline_eval.rank_race``.
Does not change scoring, freeze metadata, or the ML gate.
"""

from src.prediction_engine.facade import FreezeBackedEngine

__all__ = ["FreezeBackedEngine"]
