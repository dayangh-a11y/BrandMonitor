"""Tests for Pre-Race Decision Engine."""

from __future__ import annotations

from src.markets.scoring import RunnerContext
from src.prerace.horse_score import build_horse_scores, score_horse_today
from src.prerace.race_score import score_race_context
from src.prerace.report import format_prerace_report
from src.prerace.reports import generate_reports
from src.prerace.validate import validate_prerace, validation_blocks_publish


def _r(
    hid: int,
    name: str,
    *,
    form: float = 50,
    pr: float = 50,
    win_rate: float = 0.2,
    place_rate: float = 0.4,
    consistency: float = 60,
    starts: int = 6,
    rating: float = 70,
    improvement: float | None = 1.0,
    rest: int | None = 14,
) -> RunnerContext:
    return RunnerContext(
        horse_id=hid,
        horse_name=name,
        source_rating=rating,
        odds=None,
        starts=starts,
        wins=int(win_rate * starts),
        places=int(place_rate * starts),
        win_rate=win_rate,
        place_rate=place_rate,
        avg_finish=3.5,
        performance_rating=pr,
        sex_adjusted_pr=pr,
        form_score_5=form,
        speed_index=100.0,
        consistency_score=consistency,
        difficulty_index=40.0,
        improvement_trend=improvement,
        rest_days=rest,
        meta={
            "distance_pref_score": 0.6,
            "track_pref_score": 0.5,
            "jockey_score": 0.4,
            "trainer_score": 0.4,
            "fatigue_score": 20.0,
            "weather_pref_score": 0.5,
        },
    )


def test_race_context_scores():
    field = [_r(1, "A", form=70, pr=70), _r(2, "B", form=40, pr=40)]
    ctx = score_race_context(
        field,
        distance=1600,
        weather={"rainfall_mm": 2.0, "wind_speed_kmh": 15, "visibility_m": 8000},
    )
    assert ctx.race_strength > 0
    assert ctx.expected_pace
    assert ctx.race_shape
    assert ctx.explain.contributions
    assert "why" in ctx.explain.to_dict()


def test_horse_today_chance_and_probs():
    field = [
        _r(1, "Strong", form=80, pr=75, win_rate=0.45, rating=90),
        _r(2, "Mid", form=50, pr=50, win_rate=0.2, rating=60),
        _r(3, "Weak", form=30, pr=30, win_rate=0.05, rating=40, starts=2),
    ]
    horses = build_horse_scores(field, race_distance=1600, field_competition=60)
    assert horses[0].horse_name == "Strong"
    assert abs(sum(h.winning_probability for h in horses) - 1.0) < 1e-6
    assert horses[0].explain is not None
    assert horses[0].explain.contributions
    assert horses[0].top3_probability >= horses[0].winning_probability


def test_reports_and_validation():
    field = [
        _r(1, "Fav", form=75, pr=70, win_rate=0.4, rating=95, consistency=80),
        _r(2, "Value", form=70, pr=68, win_rate=0.35, rating=45, consistency=70),
        _r(3, "Risk", form=40, pr=40, win_rate=0.1, rating=50, consistency=20, starts=2),
    ]
    horses = build_horse_scores(field, field_competition=55)
    reports = generate_reports(horses, field)
    assert reports["best_win_candidate"]["horse"]
    assert reports["best_place_candidate"]["horse"]
    assert reports["best_win_candidate"]["why"]
    assert reports["best_win_candidate"]["metrics_contributed"]

    issues = validate_prerace(field, horses, min_starts_warn=3)
    codes = {i.code for i in issues}
    assert "insufficient_sample" in codes  # Risk has 2 starts
    assert not validation_blocks_publish(issues)

    empty_issues = validate_prerace([], [])
    assert validation_blocks_publish(empty_issues)


def test_report_text_contains_sections():
    field = [_r(1, "A"), _r(2, "B")]
    horses = build_horse_scores(field)
    reports = generate_reports(horses, field)
    payload = {
        "status": "ok",
        "publishable": True,
        "race": {"race_id": 1, "race_name": "Test", "field_size": 2},
        "race_context": score_race_context(field).to_dict(),
        "horses": [h.to_dict() for h in horses],
        "reports": reports,
        "validation": [],
    }
    text = format_prerace_report(payload)
    assert "PRE-RACE INTELLIGENCE REPORT" in text
    assert "Best Win Candidate" in text
    assert "Race Strength" in text
