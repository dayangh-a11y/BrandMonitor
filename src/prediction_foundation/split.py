"""Chronological train / validation / test splits."""

from __future__ import annotations

from typing import Iterable


def assign_time_splits(
    race_dates_sorted_unique: list[str],
    *,
    train_frac: float = 0.70,
    valid_frac: float = 0.15,
) -> dict[str, str]:
    """
    Map race_date -> split using chronological cut points on unique dates.

    TRAIN: oldest 70%
    VALIDATION: next 15%
    TEST: latest 15%
    """
    n = len(race_dates_sorted_unique)
    if n == 0:
        return {}
    train_end = max(1, int(n * train_frac))
    valid_end = max(train_end + 1, int(n * (train_frac + valid_frac)))
    if valid_end >= n:
        valid_end = n - 1 if n > 1 else n
    out: dict[str, str] = {}
    for i, d in enumerate(race_dates_sorted_unique):
        if i < train_end:
            out[d] = "TRAIN"
        elif i < valid_end:
            out[d] = "VALIDATION"
        else:
            out[d] = "TEST"
    return out


def assert_no_future_in_features(feature_race_date: str, prior_dates: Iterable[str]) -> None:
    for d in prior_dates:
        if d >= feature_race_date:
            raise AssertionError(
                f"DATA LEAKAGE: prior date {d} is not strictly before {feature_race_date}"
            )
