"""Per-metric confidence scores based on completeness and sample size.

Does NOT modify postal_score_v1. Confidence is a separate evidence grade.
"""

from __future__ import annotations

from typing import Any


def sample_size_confidence(n: int, *, full_at: int = 100) -> float:
    """Monotone confidence in [0.05, 1] from sample size."""
    n = max(0, int(n))
    if n <= 0:
        return 0.05
    return round(min(1.0, n / float(full_at)), 3)


def completeness_confidence(present_fields: int, total_fields: int) -> float:
    if total_fields <= 0:
        return 0.0
    return round(max(0.0, min(1.0, present_fields / total_fields)), 3)


def metric_confidence_bundle(
    *,
    review_count: int,
    branch_count: int,
    city_count: int,
    province_count: int,
    official_completeness_ratio: float,
    official_reachable: bool,
    target_provinces: int = 31,
    target_cities: int = 100,
    target_branches: int = 200,
    target_reviews: int = 100,
) -> dict[str, Any]:
    """
    Confidence for each dataset metric used in coverage reporting.

    Scale: 0–1. Documented, deterministic, no hidden terms.
    """
    reviews_conf = sample_size_confidence(review_count, full_at=target_reviews)
    branches_conf = sample_size_confidence(branch_count, full_at=target_branches)
    cities_conf = sample_size_confidence(city_count, full_at=target_cities)
    provinces_conf = sample_size_confidence(province_count, full_at=target_provinces)

    # geo coverage as fraction of Iran provinces/cities targets
    province_coverage_pct = round(100.0 * min(province_count, target_provinces) / target_provinces, 2)
    city_coverage_pct = round(100.0 * min(city_count, target_cities) / target_cities, 2)

    official_conf = float(official_completeness_ratio or 0.0)
    if not official_reachable:
        official_conf = min(official_conf, 0.1)

    # statistical readiness for scoring inputs that need reviews
    statistical_ready = review_count >= 30
    statistical_strong = review_count >= 100

    overall = round(
        0.35 * reviews_conf
        + 0.25 * branches_conf
        + 0.15 * provinces_conf
        + 0.10 * cities_conf
        + 0.15 * official_conf,
        3,
    )

    return {
        "metrics": {
            "reviews": {
                "value": review_count,
                "confidence": reviews_conf,
                "rule": f"min(1, n/{target_reviews})",
                "sufficient_for_stats": statistical_ready,
                "strong_for_stats": statistical_strong,
            },
            "branches": {
                "value": branch_count,
                "confidence": branches_conf,
                "rule": f"min(1, n/{target_branches})",
                "coverage_vs_target_pct": round(100.0 * min(branch_count, target_branches) / target_branches, 2),
            },
            "cities": {
                "value": city_count,
                "confidence": cities_conf,
                "coverage_pct": city_coverage_pct,
                "rule": f"min(1, n/{target_cities})",
            },
            "provinces": {
                "value": province_count,
                "confidence": provinces_conf,
                "coverage_pct": province_coverage_pct,
                "rule": f"min(1, n/{target_provinces})",
            },
            "official_profile": {
                "completeness_ratio": official_completeness_ratio,
                "reachable": official_reachable,
                "confidence": round(official_conf, 3),
                "rule": "completeness_ratio (capped if site unreachable)",
            },
        },
        "overall_dataset_confidence": overall,
        "targets": {
            "reviews": target_reviews,
            "branches": target_branches,
            "cities": target_cities,
            "provinces": target_provinces,
        },
        "notes": [
            "Confidence does not alter postal_score_v1.",
            "Reviews full confidence at n>=100; statistical minimum treated as n>=30.",
        ],
    }
