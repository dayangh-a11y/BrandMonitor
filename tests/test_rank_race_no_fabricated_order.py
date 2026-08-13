"""Unit tests for baseline rank_race — no fabricated cloth-order ranks."""

from __future__ import annotations

from src.prediction_foundation.baseline_eval import rank_race, score_A_historical


def _row(result_id: int, **features: object) -> dict:
    row: dict = {"result_id": result_id, "horse_id": result_id, "race_id": 1}
    for name, value in features.items():
        if value is None:
            row[f"{name}__value"] = None
            row[f"{name}__is_missing"] = True
        else:
            row[f"{name}__value"] = value
            row[f"{name}__is_missing"] = False
    return row


def test_rank_race_all_missing_scores_have_null_ranks() -> None:
    horses = [_row(10), _row(11), _row(12)]
    ranked = rank_race(horses, score_A_historical)
    assert all(h["pred_score"] is None for h in ranked)
    assert all(h["pred_rank"] is None for h in ranked)


def test_rank_race_only_scored_horses_receive_ranks() -> None:
    horses = [
        _row(1),  # unscored, lowest result_id (would have been fake #1 before)
        _row(2, career_avg_finish=4.0, career_win_rate=0.1, career_top3_rate=0.3),
        _row(3, career_avg_finish=2.0, career_win_rate=0.4, career_top3_rate=0.6),
    ]
    ranked = rank_race(horses, score_A_historical)
    scored = [h for h in ranked if h["pred_rank"] is not None]
    unscored = [h for h in ranked if h["pred_rank"] is None]
    assert len(scored) == 2
    assert len(unscored) == 1
    assert unscored[0]["result_id"] == 1
    assert scored[0]["result_id"] == 3  # better form
    assert scored[0]["pred_rank"] == 1
    assert scored[1]["result_id"] == 2
    assert scored[1]["pred_rank"] == 2
