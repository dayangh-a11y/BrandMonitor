"""Prediction market (mosharekat.asbdavani.app) integration."""

from __future__ import annotations

from src.prediction_market.build import build_prediction_analytics
from src.prediction_market.collect import collect_prediction_history
from src.prediction_market.discover import discover_prediction_fields

__all__ = [
    "build_prediction_analytics",
    "collect_prediction_history",
    "discover_prediction_fields",
]
