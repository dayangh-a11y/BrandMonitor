"""Tests for redesigned ranking eligibility and PR (no earnings dominance)."""

from __future__ import annotations

from src.analytics.metrics import performance_rating
from src.analytics.ranking import (
    qualify_for_board,
    sample_size_confidence,
    season_best_gate,
)


def test_sample_size_confidence_bands() -> None:
    assert sample_size_confidence(1).level == "very_low"
    assert sample_size_confidence(2).level == "low"
    assert sample_size_confidence(3).level == "medium"
    assert sample_size_confidence(5).level == "valid"
    assert sample_size_confidence(10).level == "high"


def test_season_best_gate_single_start_universe() -> None:
    gate = season_best_gate(starts_list=[1, 1, 1, 1], minimum_starts=5)
    assert gate["status"] == "INSUFFICIENT_DATA"
    assert gate["message"] == "INSUFFICIENT DATA"


def test_season_best_gate_ok_when_qualified() -> None:
    gate = season_best_gate(starts_list=[1, 5, 8, 2], minimum_starts=5)
    assert gate["status"] == "OK"
    assert gate["horses_qualified"] == 2


def test_qualify_excludes_below_minimum() -> None:
    q = qualify_for_board(starts=1, minimum_starts=5, board="best_season")
    assert q.qualified is False
    assert q.status == "excluded"
    assert q.reason_exclusion is not None


def test_performance_rating_excludes_earnings_by_default() -> None:
    low_earn = performance_rating(
        starts=5,
        wins=3,
        seconds=1,
        thirds=0,
        win_rate=0.6,
        place_rate=0.8,
        avg_finish=2.0,
        consistency=80.0,
        speed_index=100.0,
        earnings_index=0.1,
        difficulty_index=50.0,
        form_score=70.0,
        include_earnings=False,
    )
    high_earn = performance_rating(
        starts=5,
        wins=3,
        seconds=1,
        thirds=0,
        win_rate=0.6,
        place_rate=0.8,
        avg_finish=2.0,
        consistency=80.0,
        speed_index=100.0,
        earnings_index=1.0,
        difficulty_index=50.0,
        form_score=70.0,
        include_earnings=False,
    )
    assert low_earn == high_earn


def test_performance_rating_single_win_not_maxed_by_prize() -> None:
    """One-start winners must not be ordered solely by purse inside PR."""
    a = performance_rating(
        starts=1,
        wins=1,
        seconds=0,
        thirds=0,
        avg_finish=1.0,
        consistency=100.0,
        speed_index=101.0,
        earnings_index=1.0,
        difficulty_index=40.0,
        form_score=100.0,
    )
    b = performance_rating(
        starts=1,
        wins=1,
        seconds=0,
        thirds=0,
        avg_finish=1.0,
        consistency=100.0,
        speed_index=101.0,
        earnings_index=0.5,
        difficulty_index=40.0,
        form_score=100.0,
    )
    assert a == b
