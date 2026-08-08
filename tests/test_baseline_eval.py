"""Tests for dataset freeze + baseline scoring helpers."""

from __future__ import annotations

from src.prediction_foundation.baseline_eval import (
    score_A_historical,
    score_C_recent_form,
    score_D_contextual,
    wilson_interval,
)
def test_wilson_interval_bounds():
    lo, hi = wilson_interval(20, 100)
    assert lo is not None and hi is not None
    assert 0 <= lo < 0.2 < hi <= 1


def test_historical_score_uses_pre_race_cells_only():
    row = {
        "career_avg_finish__value": 2.0,
        "career_avg_finish__is_missing": False,
        "career_win_rate__value": 0.4,
        "career_win_rate__is_missing": False,
        "career_top3_rate__value": 0.6,
        "career_top3_rate__is_missing": False,
    }
    s = score_A_historical(row)
    assert s is not None and s > 50


def test_recent_form_missing_returns_none():
    row = {
        "avg_finish_last5__is_missing": True,
        "win_rate_last5__is_missing": True,
        "form_trend__is_missing": True,
        "last_finish__is_missing": True,
    }
    assert score_C_recent_form(row) is None


def test_contextual_falls_back_when_empty():
    row = {
        "career_avg_finish__value": 3.0,
        "career_avg_finish__is_missing": False,
        "avg_finish_last5__is_missing": True,
        "track_win_rate__is_missing": True,
        "win_rate_same_distance__is_missing": True,
        "breed_win_rate__is_missing": True,
        "trainer_win_rate_prior__is_missing": True,
        "career_win_rate__is_missing": True,
        "trainer_recent_form__is_missing": True,
        "assigned_weight__is_missing": True,
    }
    assert score_D_contextual(row) is not None
