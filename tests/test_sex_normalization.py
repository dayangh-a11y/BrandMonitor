"""Tests for Sex Normalization Engine."""

from __future__ import annotations

from datetime import date

import pytest

from src.analytics.metrics import StartRec
from src.analytics.sex_normalize import (
    adjust_start_quality,
    annotate_starts,
    build_race_compositions,
    compute_all_sex_metrics,
    estimate_sex_strength_factor,
    finish_quality,
    normalize_biological_sex,
    resolve_sex_for_start,
    RaceSexComposition,
    SexStrengthFactor,
)


def _start(
    horse_id: int,
    race_id: int,
    finish: int,
    *,
    name: str = "H",
    birthdate: date | None = None,
    race_date: date | None = None,
) -> StartRec:
    return StartRec(
        horse_id=horse_id,
        horse_name=name,
        race_id=race_id,
        race_date=race_date or date(2026, 1, 1),
        racecourse_code="test",
        breed="ترکمن",
        distance=1600,
        race_name="test",
        finish=finish,
        time_raw=None,
        source_rating=50.0,
        prize=0.0,
        jockey=None,
        trainer=None,
        owner=None,
        sire=None,
        birthdate=birthdate,
        field_size=4,
    )


def test_normalize_sex_labels():
    assert normalize_biological_sex("نر", age_years_value=3) == "Colt"
    assert normalize_biological_sex("نر", age_years_value=6) == "Stallion"
    assert normalize_biological_sex("ماده", age_years_value=3) == "Filly"
    assert normalize_biological_sex("ماده", age_years_value=6) == "Mare"
    assert normalize_biological_sex("اخته") == "Gelding"
    assert normalize_biological_sex("نر") == "Stallion"  # age unknown → adult
    assert normalize_biological_sex("ماده") == "Mare"
    assert normalize_biological_sex(None) == "Unknown"


def test_race_composition_and_ssf_from_history():
    # Mixed races where males finish better on average
    starts = []
    raw = {}
    for race_id in range(1, 8):
        starts.append(_start(1, race_id, 1, name="MaleA"))  # male wins
        starts.append(_start(2, race_id, 2, name="MaleB"))
        starts.append(_start(3, race_id, 3, name="FemA"))
        starts.append(_start(4, race_id, 4, name="FemB"))
        raw[1] = "نر"
        raw[2] = "نر"
        raw[3] = "ماده"
        raw[4] = "ماده"

    sex_by = {
        (s.horse_id, s.race_id): resolve_sex_for_start(s, raw.get(s.horse_id))
        for s in starts
    }
    comps = build_race_compositions(starts, sex_by)
    assert comps[1].mixed is True
    assert comps[1].males == 2
    assert comps[1].females == 2

    ssf = estimate_sex_strength_factor(starts, sex_by, comps, min_mixed_races=5)
    assert ssf.method == "mixed_race_mean_quality_gap"
    assert ssf.factor > 0  # males stronger historically
    assert ssf.mixed_races_used >= 5


def test_female_gets_credit_against_males():
    ssf = SexStrengthFactor(
        factor=20.0,
        mixed_races_used=10,
        male_starts=20,
        female_starts=20,
        male_mean_quality=70.0,
        female_mean_quality=50.0,
        male_mean_finish=2.0,
        female_mean_finish=3.0,
        method="test",
    )
    comp = RaceSexComposition(
        race_id=1, males=5, females=5, unknown=0, field_size=10, mixed=True
    )
    raw_q = finish_quality(3)
    adj_q, _ = adjust_start_quality(
        raw_quality=raw_q, group="female", composition=comp, ssf=ssf
    )
    assert adj_q > raw_q  # mare credited
    adj_male, _ = adjust_start_quality(
        raw_quality=raw_q, group="male", composition=comp, ssf=ssf
    )
    assert adj_male == raw_q  # males not boosted


def test_sex_adjusted_metrics_pipeline():
    starts = []
    raw = {1: "ماده", 2: "نر", 3: "نر"}
    for race_id in range(1, 6):
        starts.append(_start(1, race_id, 2, name="Mare1"))
        starts.append(_start(2, race_id, 1, name="Stallion1"))
        starts.append(_start(3, race_id, 3, name="Stallion2"))

    ssf, comps, metrics = compute_all_sex_metrics(
        starts, raw, scope="season", season_key="test"
    )
    by_id = {m.horse_id: m for m in metrics}
    mare = by_id[1]
    assert mare.sex in {"Mare", "Filly"}
    assert mare.starts_mixed == 5
    assert mare.sex_adjusted_performance_rating is not None
    # With positive SSF, mare adjusted PR should be >= raw contribution path
    assert mare.explain["sex_credit"] >= 0
    assert all(c.mixed for c in comps.values())
