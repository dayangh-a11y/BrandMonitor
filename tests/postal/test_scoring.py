"""Tests for explainable postal scoring."""

from __future__ import annotations

from postal.dimensions import (
    score_customer_satisfaction,
    score_delivery_speed,
    score_pricing,
    score_service_variety,
    score_transparency,
)
from postal.scoring import compute_branch_score, compute_company_score
from postal.weights import load_scoring_config, normalized_weights


def test_weights_sum_to_one():
    w = normalized_weights()
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert set(w) >= {
        "customer_satisfaction",
        "delivery_speed",
        "service_coverage",
        "pricing",
        "service_variety",
        "transparency",
        "complaint_rate",
        "branch_quality",
    }


def test_customer_satisfaction_explainable():
    result = score_customer_satisfaction(
        sentiments={"Positive": 6, "Neutral": 2, "Negative": 2},
        avg_rating=3.5,
        review_count=10,
    )
    assert 0 <= result.score <= 100
    assert "CSI" in result.formula or "csi" in result.formula.lower()
    assert result.explanation
    assert result.inputs["n"] == 10


def test_delivery_speed_faster_is_better():
    bm = {"excellent_days": 1.0, "poor_days": 7.0}
    fast = score_delivery_speed(intercity_typical_days=1.0, benchmarks=bm)
    slow = score_delivery_speed(intercity_typical_days=7.0, benchmarks=bm)
    assert fast.score > slow.score


def test_pricing_lower_index_better():
    bm = {"best_index": 0.7, "worst_index": 1.4}
    cheap = score_pricing(price_index=0.7, benchmarks=bm)
    expensive = score_pricing(price_index=1.4, benchmarks=bm)
    assert cheap.score > expensive.score


def test_company_score_weighted_sum():
    official = {
        "services": ["domestic_express", "tracking", "cod", "insurance", "packaging", "door_to_door"],
        "cities_covered_official": 200,
        "provinces_covered_official": 31,
        "branch_count_official": 400,
        "official_pricing": {"price_index": 1.0, "base_parcel_0_to_1kg_toman": 80000},
        "official_delivery_times": {"intercity_typical_days": 2},
        "tracking": {"available": True},
        "insurance": {"available": True},
        "working_hours": {"weekdays": "8-18"},
        "customer_support": {"phone": ["123"]},
        "cod": {"available": True},
    }
    breakdown = compute_company_score(
        company_slug="demo",
        company_name="Demo",
        official=official,
        review_stats={
            "sentiments": {"Positive": 5, "Neutral": 3, "Negative": 2},
            "avg_rating": 3.2,
            "review_count": 10,
            "complaints": {"delivery_delay": 2},
        },
        branch_stats={
            "observed_branch_count": 10,
            "avg_google_rating": 3.5,
            "branch_scores": [55.0, 60.0, 50.0],
        },
    )
    assert 0 <= breakdown.score <= 100
    assert breakdown.why
    assert "weighted_contribution" in breakdown.to_dict()
    # Reconstruct score from contributions
    recon = sum(breakdown.weights[k] * breakdown.dimensions[k].score for k in breakdown.weights)
    assert abs(recon - breakdown.score) < 0.05


def test_branch_score_shrinks_with_few_reviews():
    low_n, exp_low = compute_branch_score(
        avg_rating=5.0,
        sentiments={"Positive": 1},
        complaints={},
        review_count=1,
    )
    high_n, exp_high = compute_branch_score(
        avg_rating=5.0,
        sentiments={"Positive": 40},
        complaints={},
        review_count=40,
    )
    assert exp_low["inputs"]["kappa"] < exp_high["inputs"]["kappa"]
    assert high_n >= low_n


def test_transparency_checklist():
    r = score_transparency(
        tracking={"available": True},
        insurance={"available": True},
        pricing={"price_index": 1.0},
        working_hours={"weekdays": "8-18"},
        support={"phone": ["1"]},
        cod={"available": False},
    )
    assert r.score == 100.0
    assert len(r.inputs["checks"]) == 6


def test_service_variety():
    r = score_service_variety(services=["tracking", "cod", "insurance"])
    assert 0 < r.score < 100
    assert r.inputs["matched"] == 3
