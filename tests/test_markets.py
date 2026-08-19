"""Tests for Market-Specific Analytics Engine."""

from __future__ import annotations

from src.markets.answer import format_market_answer
from src.markets.h2h import build_pairwise_matrix, pairwise_compare
from src.markets.matchup import analyze_matchup, parse_matchup_query
from src.markets.place import analyze_place_market, place_strength
from src.markets.risk import analyze_risk_market
from src.markets.scoring import RunnerContext, detect_favorite
from src.markets.surprise import analyze_surprise_market
from src.markets.value import analyze_value_market
from src.markets.win import analyze_win_market, win_strength
from src.markets.without_favorite import analyze_without_favorite


def _runner(
    hid: int,
    name: str,
    *,
    win_rate: float = 0.2,
    place_rate: float = 0.4,
    pr: float = 50.0,
    form: float = 50.0,
    rating: float | None = 60.0,
    odds: float | None = None,
    consistency: float = 60.0,
    starts: int = 8,
    improvement: float | None = 0.0,
) -> RunnerContext:
    return RunnerContext(
        horse_id=hid,
        horse_name=name,
        source_rating=rating,
        odds=odds,
        starts=starts,
        wins=int(win_rate * starts),
        places=int(place_rate * starts),
        win_rate=win_rate,
        place_rate=place_rate,
        avg_finish=3.5,
        performance_rating=pr,
        form_score_5=form,
        speed_index=100.0,
        consistency_score=consistency,
        difficulty_index=40.0,
        improvement_trend=improvement,
    )


def test_win_and_place_use_different_models():
    a = _runner(1, "A", win_rate=0.5, place_rate=0.5, pr=70, form=70, rating=90)
    b = _runner(2, "B", win_rate=0.1, place_rate=0.8, pr=55, form=80, consistency=90, rating=50)
    # Win model should prefer high win_rate A; Place may prefer consistent B
    assert win_strength(a) > win_strength(b)
    # Place strength weights place_rate/consistency heavily
    assert place_strength(b) > place_strength(_runner(3, "C", win_rate=0.6, place_rate=0.2, consistency=20))

    win_ans = analyze_win_market([a, b])
    place_ans = analyze_place_market([a, b])
    assert win_ans.market == "WIN"
    assert place_ans.market == "PLACE"
    assert win_ans.applicable_market != place_ans.applicable_market
    assert "win_rate" in win_ans.metrics_used
    assert "place_rate" in place_ans.metrics_used
    assert win_ans.prediction["winner"]["horse"] == "A"


def test_without_favorite_excludes_top_rated():
    fav = _runner(1, "Fav", rating=100, odds=1.8, win_rate=0.4, pr=65)
    a = _runner(2, "A", rating=70, odds=4.0, win_rate=0.35, pr=62)
    b = _runner(3, "B", rating=60, odds=6.0, win_rate=0.25, pr=55)
    picked, how = detect_favorite([fav, a, b])
    assert picked.horse_name == "Fav"
    assert how == "lowest odds"
    ans = analyze_without_favorite([fav, a, b])
    pred = ans.prediction
    assert pred["excluded_favorite"]["horse"] == "Fav"
    assert pred["best_remaining"]["horse"] in {"A", "B"}
    assert pred["best_remaining"]["horse"] != "Fav"


def test_value_and_surprise_and_risk():
    field = [
        _runner(1, "PublicFav", rating=95, odds=2.0, win_rate=0.15, pr=45, form=40),
        _runner(2, "Value", rating=50, odds=8.0, win_rate=0.4, pr=70, form=75),
        _runner(3, "Improver", rating=55, odds=7.0, win_rate=0.2, pr=50, form=60, improvement=5.0),
    ]
    val = analyze_value_market(field)
    assert val.prediction["top_value"]["horse"] == "Value"
    sur = analyze_surprise_market(field)
    assert sur.prediction["most_overrated_horse"]["horse"] == "PublicFav"
    assert sur.prediction["most_underrated_horse"]["horse"] == "Value"
    risk = analyze_risk_market(field)
    assert "safest" in risk.prediction
    assert risk.market == "RISK"


def test_pairwise_matrix_complete():
    field = [
        _runner(1, "A", win_rate=0.4, pr=70),
        _runner(2, "B", win_rate=0.3, pr=60),
        _runner(3, "C", win_rate=0.2, pr=50),
    ]
    matrix = build_pairwise_matrix(field)
    assert len(matrix) == 3  # C(3,2)=3
    pair = pairwise_compare(field[0], field[1])
    assert abs(pair.a_ahead_prob + pair.b_ahead_prob - 1.0) < 1e-6
    ans = analyze_win_market(field)
    assert ans.sample_size > 0


def test_matchup_not_season_ranking():
    a = _runner(1, "دنزی بوی", win_rate=0.35, pr=66, form=70, rating=70)
    b = _runner(2, "لیدی سانگ", win_rate=0.25, pr=58, form=55, rating=80)
    a.sex = "Stallion"
    b.sex = "Mare"
    ans = analyze_matchup(a, b)
    assert ans.market == "MATCHUP"
    assert "Season ranking was NOT used" in " ".join(ans.reasons)
    assert 0 < ans.prediction["probability_a_finishes_ahead"] < 1
    assert len(ans.prediction["factors"]) >= 10
    text = format_market_answer(ans)
    assert "Direct Matchup" in text
    assert "Confidence:" in text


def test_parse_persian_matchup():
    assert parse_matchup_query("دنزی بوی یا لیدی سانگ") == ("دنزی بوی", "لیدی سانگ")
    assert parse_matchup_query("A vs B") == ("A", "B")
    assert parse_matchup_query("only one name") is None


def test_answer_schema_complete():
    ans = analyze_win_market([_runner(1, "X"), _runner(2, "Y")])
    d = ans.to_dict()
    for key in (
        "prediction",
        "confidence",
        "reasons",
        "metrics_used",
        "sample_size",
        "data_quality",
        "applicable_market",
    ):
        assert key in d
