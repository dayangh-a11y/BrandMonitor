"""Empirical-Bayes / small-sample helpers."""

from __future__ import annotations


def eb_rate(successes: int, trials: int, prior_mean: float, prior_strength: float = 5.0) -> float | None:
    if trials <= 0:
        return None
    return (successes + prior_strength * prior_mean) / (trials + prior_strength)


def form_trend(finishes: list[int]) -> float | None:
    """Positive = improving (lower finish numbers recently).

    Compares mean of older half vs newer half of the provided window.
    """
    if len(finishes) < 2:
        return None
    mid = len(finishes) // 2
    older = finishes[:mid]
    newer = finishes[mid:]
    if not older or not newer:
        return None
    return (sum(older) / len(older)) - (sum(newer) / len(newer))
