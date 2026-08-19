"""Shared runner context + scoring primitives for market models."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from statistics import mean, pstdev
from typing import Any

from src.analytics.metrics import clamp


@dataclass
class RunnerContext:
    horse_id: int
    horse_name: str
    cloth: int | None = None
    source_rating: float | None = None
    odds: float | None = None
    # Career / season metrics (optional — filled when available)
    starts: int = 0
    wins: int = 0
    places: int = 0
    win_rate: float | None = None
    place_rate: float | None = None
    avg_finish: float | None = None
    performance_rating: float | None = None
    sex_adjusted_pr: float | None = None
    form_score_5: float | None = None
    speed_index: float | None = None
    consistency_score: float | None = None
    difficulty_index: float | None = None
    improvement_trend: float | None = None
    age_years: float | None = None
    sex: str | None = None
    trainer: str | None = None
    jockey: str | None = None
    weight: float | None = None
    rest_days: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def strength(self) -> float:
        """Generic racing strength 0..100 — NOT a market score by itself."""
        parts: list[tuple[float, float]] = []
        pr = self.sex_adjusted_pr if self.sex_adjusted_pr is not None else self.performance_rating
        if pr is not None:
            parts.append((0.35, float(pr)))
        if self.form_score_5 is not None:
            parts.append((0.25, float(self.form_score_5)))
        if self.speed_index is not None:
            parts.append((0.15, clamp(float(self.speed_index), 50, 150) - 50))  # rough 0..100
        if self.win_rate is not None:
            parts.append((0.15, float(self.win_rate) * 100.0))
        if self.source_rating is not None and self.source_rating > 0:
            parts.append((0.10, clamp((float(self.source_rating) - 30.0) * 1.1)))
        if not parts:
            return 40.0
        tw = sum(w for w, _ in parts)
        return clamp(sum(w * v for w, v in parts) / tw)


def softmax_probs(scores: dict[int, float], *, temperature: float = 12.0) -> dict[int, float]:
    """Convert arbitrary scores to probabilities (higher score → higher p)."""
    if not scores:
        return {}
    # temperature scales softness
    t = max(1e-6, float(temperature))
    exps = {k: math.exp(float(v) / t) for k, v in scores.items()}
    total = sum(exps.values()) or 1.0
    return {k: v / total for k, v in exps.items()}


def top_k_probability(win_probs: dict[int, float], k: int) -> dict[int, float]:
    """
    Approximate Top-k finish probability from independent win probs
    via 1 - (1-p)^k heuristic adjusted by field size.
    """
    n = max(1, len(win_probs))
    out: dict[int, float] = {}
    for hid, p in win_probs.items():
        # Soft top-k: blend win prob with cumulative field share
        out[hid] = clamp(1.0 - (1.0 - p) ** max(1, k) * (n / (n + k * 0.5)), 0.0, 1.0)
    # renormalize lightly so mean is sensible
    return out


def public_perception_score(runner: RunnerContext, field: list[RunnerContext]) -> float | None:
    """0..100 public perception from odds (preferred) or source_rating rank."""
    with_odds = [r for r in field if r.odds is not None and r.odds > 0]
    if with_odds and runner.odds is not None and runner.odds > 0:
        inv = {r.horse_id: 1.0 / float(r.odds) for r in with_odds}
        total = sum(inv.values()) or 1.0
        return clamp(100.0 * inv.get(runner.horse_id, 0.0) / total * len(inv))
    rated = [r for r in field if r.source_rating is not None and r.source_rating > 0]
    if not rated or runner.source_rating is None or runner.source_rating <= 0:
        return None
    # percentile among ratings
    better = sum(1 for r in rated if (r.source_rating or 0) > (runner.source_rating or 0))
    rank = better + 1
    return clamp(100.0 * (1.0 - (rank - 1) / max(1, len(rated) - 1))) if len(rated) > 1 else 50.0


def detect_favorite(field: list[RunnerContext]) -> tuple[RunnerContext | None, str]:
    """Strongest public favorite: lowest odds, else highest source_rating, else strength."""
    with_odds = [r for r in field if r.odds is not None and r.odds > 0]
    if with_odds:
        return min(with_odds, key=lambda r: float(r.odds or 9999)), "lowest odds"
    rated = [r for r in field if r.source_rating is not None and r.source_rating > 0]
    if rated:
        return max(rated, key=lambda r: float(r.source_rating or 0)), "highest source_rating"
    if not field:
        return None, "none"
    return max(field, key=lambda r: r.strength), "highest model strength"


def variance_of_finishes(finishes: list[int]) -> float | None:
    vals = [f for f in finishes if f and f > 0]
    if len(vals) < 2:
        return 0.0 if len(vals) == 1 else None
    return float(pstdev(vals))


def reliability_from_consistency(consistency: float | None, starts: int) -> float:
    if consistency is None:
        return 30.0 if starts > 0 else 0.0
    sample = clamp(starts * 8.0)
    return clamp(0.7 * float(consistency) + 0.3 * sample)
