"""Unit tests for prediction foundation (leakage + feature cells)."""

from __future__ import annotations

from datetime import date

from src.prediction_foundation.compute import compute_features, compute_targets
from src.prediction_foundation.dictionary import FEATURE_DICTIONARY
from src.prediction_foundation.leakage import run_leakage_audit
from src.prediction_foundation.readiness import assess_readiness
from src.prediction_foundation.split import assign_time_splits
from src.prediction_foundation.types import ObservationKeys


def _keys(**kwargs):
    base = dict(
        result_id=1,
        race_id=10,
        horse_id=100,
        warehouse_horse_id=200,
        race_date="2024-06-01",
        track="مشهد",
        distance=1000,
        surface="تروبرد",
        race_name="کلاس6",
        class_code="handicap_band",
        age_category=None,
        trainer_id=5,
        owner_id=7,
        weight=56.0,
        field_size=8,
        finish_position=2,
    )
    base.update(kwargs)
    return ObservationKeys(**base)


def test_features_use_only_prior_history():
    priors = [
        {
            "race_date": date(2024, 1, 1),
            "finish": 1,
            "track": "مشهد",
            "dist": 1000,
            "surface": "تروبرد",
            "class_code": "handicap_band",
        },
        {
            "race_date": date(2024, 3, 1),
            "finish": 3,
            "track": "گنبدکاووس",
            "dist": 1200,
            "surface": "تروبرد",
            "class_code": "handicap_band",
        },
    ]
    feats = compute_features(
        _keys(),
        horse_priors=priors,
        trainer_priors=priors,
        owner_priors=priors * 3,  # n>=5 for owner rates
    )
    assert feats["career_starts_before_race"].value == 2
    assert feats["career_wins_before_race"].value == 1
    assert feats["last_finish"].value == 3
    assert feats["starts_same_distance"].value == 1
    assert feats["starts_at_track"].value == 1
    assert feats["career_win_rate"].raw_rate == 0.5
    assert feats["career_win_rate"].smoothed_rate is not None
    assert feats["career_win_rate"].is_missing is False


def test_debut_missing_rates_not_zero_fake():
    feats = compute_features(
        _keys(),
        horse_priors=[],
        trainer_priors=[],
        owner_priors=[],
    )
    assert feats["career_starts_before_race"].value == 0
    assert feats["career_win_rate"].is_missing is True
    assert feats["career_win_rate"].value is None
    assert feats["days_since_last_race"].is_missing is True


def test_class_not_invented_when_missing():
    feats = compute_features(
        _keys(class_code=None),
        horse_priors=[],
        trainer_priors=[],
        owner_priors=[],
    )
    assert feats["race_class"].is_missing is True
    assert feats["starts_same_class"].is_missing is True
    assert feats["class_win_rate"].is_missing is True


def test_targets_isolated():
    t = compute_targets(1)
    assert t == {"target_win": 1, "target_top3": 1, "target_finish": 1}
    t2 = compute_targets(None)
    assert t2["target_win"] is None


def test_chronological_split_order():
    dates = [f"2020-01-{d:02d}" for d in range(1, 11)]
    m = assign_time_splits(dates, train_frac=0.7, valid_frac=0.15)
    assert m[dates[0]] == "TRAIN"
    assert m[dates[-1]] == "TEST"
    # no TEST date before TRAIN
    train_idxs = [i for i, d in enumerate(dates) if m[d] == "TRAIN"]
    test_idxs = [i for i, d in enumerate(dates) if m[d] == "TEST"]
    assert max(train_idxs) < min(test_idxs)


def test_dictionary_and_leakage_audit():
    assert len(FEATURE_DICTIONARY) >= 40
    audit = run_leakage_audit()
    assert audit["betting_data_used"] is False
    assert audit["targets_leak_into_features"] is False


def test_readiness_yes_path():
    r = assess_readiness(
        observation_count=1000,
        coverage={"features": []},
        leakage={
            "betting_data_used": False,
            "future_results_used_in_features": False,
            "targets_leak_into_features": False,
            "medium_or_higher_features": [],
        },
        class_available_pct=25.0,
        linked_horse_pct=99.0,
    )
    assert r["can_create_leakage_safe_training_dataset"] == "YES"
