"""Explainable 0–100 dimension scorers for postal companies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DimensionResult:
    key: str
    score: float
    inputs: dict[str, Any] = field(default_factory=dict)
    formula: str = ""
    explanation: str = ""


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _lerp_inv(value: float, best: float, worst: float) -> float:
    """Map value onto 0–100 where `best` → 100 and `worst` → 0."""
    if abs(worst - best) < 1e-9:
        return 50.0
    t = (value - best) / (worst - best)
    return _clamp(100.0 * (1.0 - t))


def score_customer_satisfaction(
    *,
    sentiments: dict[str, int],
    avg_rating: float,
    review_count: int,
) -> DimensionResult:
    n = sum(sentiments.values()) or 0
    if n == 0 and review_count == 0:
        return DimensionResult(
            key="customer_satisfaction",
            score=50.0,
            inputs={"sentiments": sentiments, "avg_rating": avg_rating, "n": 0},
            formula="prior 50 when no reviews",
            explanation="No customer reviews available; using neutral prior 50.",
        )
    pos = sentiments.get("Positive", 0)
    neu = sentiments.get("Neutral", 0)
    neg = sentiments.get("Negative", 0)
    csi = 100.0 * (pos + 0.5 * neu) / max(n, 1)
    rating_score = _clamp((float(avg_rating) / 5.0) * 100.0)
    # Blend: 60% CSI + 40% star rating
    score = _clamp(0.60 * csi + 0.40 * rating_score)
    return DimensionResult(
        key="customer_satisfaction",
        score=round(score, 2),
        inputs={
            "sentiments": dict(sentiments),
            "n": n,
            "csi": round(csi, 2),
            "avg_rating": round(float(avg_rating), 3),
            "rating_score": round(rating_score, 2),
        },
        formula="0.60 * CSI + 0.40 * (avg_rating/5*100); CSI=(pos+0.5*neu)/n*100",
        explanation=(
            f"CSI={csi:.1f} from {pos}/{neu}/{neg} (pos/neu/neg) over {n} analyzed reviews; "
            f"rating_score={rating_score:.1f} from avg {avg_rating:.2f}/5 → {score:.1f}."
        ),
    )


def score_delivery_speed(
    *,
    intercity_typical_days: float,
    benchmarks: dict[str, float],
) -> DimensionResult:
    excellent = float(benchmarks.get("excellent_days", 1.0))
    poor = float(benchmarks.get("poor_days", 7.0))
    days = float(intercity_typical_days)
    score = _lerp_inv(days, excellent, poor)
    return DimensionResult(
        key="delivery_speed",
        score=round(score, 2),
        inputs={
            "intercity_typical_days": days,
            "excellent_days": excellent,
            "poor_days": poor,
        },
        formula="linear map: excellent_days→100, poor_days→0 using official intercity_typical_days",
        explanation=(
            f"Official intercity typical delivery {days} days "
            f"(benchmarks {excellent}→100, {poor}→0) → {score:.1f}."
        ),
    )


def score_service_coverage(
    *,
    cities: int,
    provinces: int,
    branches: int,
    observed_branches: int,
    benchmarks: dict[str, float],
) -> DimensionResult:
    # Prefer max(official, observed) for branch footprint
    branch_eff = max(int(branches), int(observed_branches))
    tc = float(benchmarks.get("target_cities", 200))
    tp = float(benchmarks.get("target_provinces", 31))
    tb = float(benchmarks.get("target_branches", 400))
    city_s = _clamp(100.0 * min(cities, tc) / tc)
    prov_s = _clamp(100.0 * min(provinces, tp) / tp)
    branch_s = _clamp(100.0 * min(branch_eff, tb) / tb)
    # Soft-cap mega networks (national post) so they don't auto-win everything:
    # still high, but blend keeps room for quality dimensions.
    score = _clamp(0.40 * city_s + 0.25 * prov_s + 0.35 * branch_s)
    return DimensionResult(
        key="service_coverage",
        score=round(score, 2),
        inputs={
            "cities_official": cities,
            "provinces_official": provinces,
            "branches_official": branches,
            "branches_observed": observed_branches,
            "branch_effective": branch_eff,
            "city_score": round(city_s, 2),
            "province_score": round(prov_s, 2),
            "branch_score": round(branch_s, 2),
        },
        formula="0.40*min(cities/target_cities,1)*100 + 0.25*provinces + 0.35*branches",
        explanation=(
            f"Coverage from cities={cities}, provinces={provinces}, "
            f"branches_eff={branch_eff} → {score:.1f}."
        ),
    )


def score_pricing(*, price_index: float, benchmarks: dict[str, float]) -> DimensionResult:
    best = float(benchmarks.get("best_index", 0.70))
    worst = float(benchmarks.get("worst_index", 1.40))
    idx = float(price_index)
    score = _lerp_inv(idx, best, worst)
    return DimensionResult(
        key="pricing",
        score=round(score, 2),
        inputs={"price_index": idx, "best_index": best, "worst_index": worst},
        formula="lower official price_index → higher score (best_index→100, worst_index→0)",
        explanation=f"Official price_index={idx:.2f} mapped to {score:.1f} (lower is better).",
    )


def score_service_variety(*, services: list[str], catalog: list[str] | None = None) -> DimensionResult:
    catalog = catalog or [
        "domestic_express",
        "domestic_economy",
        "door_to_door",
        "branch_to_branch",
        "international",
        "insurance",
        "cod",
        "tracking",
        "packaging",
        "pickup",
        "registered_mail",
        "urban_ondemand",
    ]
    have = {s for s in services if s in catalog}
    score = _clamp(100.0 * len(have) / max(len(catalog), 1))
    return DimensionResult(
        key="service_variety",
        score=round(score, 2),
        inputs={"services": sorted(have), "catalog_size": len(catalog), "matched": len(have)},
        formula="100 * |services ∩ catalog| / |catalog|",
        explanation=f"Offers {len(have)}/{len(catalog)} catalog services → {score:.1f}.",
    )


def score_transparency(
    *,
    tracking: dict[str, Any],
    insurance: dict[str, Any],
    pricing: dict[str, Any],
    working_hours: dict[str, Any],
    support: dict[str, Any],
    cod: dict[str, Any],
) -> DimensionResult:
    checks = {
        "tracking_available": bool((tracking or {}).get("available")),
        "insurance_disclosed": bool((insurance or {}).get("available"))
        or bool((insurance or {}).get("notes")),
        "pricing_published": bool((pricing or {}).get("base_parcel_0_to_1kg_toman"))
        or bool((pricing or {}).get("price_index")),
        "hours_published": bool(working_hours),
        "support_phone": bool((support or {}).get("phone")),
        "cod_policy_disclosed": "available" in (cod or {}),
    }
    score = _clamp(100.0 * sum(1 for v in checks.values() if v) / len(checks))
    return DimensionResult(
        key="transparency",
        score=round(score, 2),
        inputs={"checks": checks},
        formula="100 * (# disclosed transparency checks) / 6",
        explanation=(
            "Transparency checklist: "
            + ", ".join(f"{k}={'yes' if v else 'no'}" for k, v in checks.items())
            + f" → {score:.1f}."
        ),
    )


def score_complaint_rate(*, sentiments: dict[str, int], complaints: dict[str, int]) -> DimensionResult:
    n = sum(sentiments.values()) or 0
    if n == 0:
        return DimensionResult(
            key="complaint_rate",
            score=50.0,
            inputs={"n": 0, "complaints": complaints},
            formula="prior 50 when no reviews",
            explanation="No reviews to estimate complaint rate; prior 50.",
        )
    complaint_events = sum(complaints.values())
    # Rate relative to reviews; cap influence
    rate = complaint_events / n
    # 0 complaints → 100; rate 1.0 → ~20; rate ≥1.5 → ~0
    score = _clamp(100.0 - 60.0 * rate)
    neg_share = sentiments.get("Negative", 0) / n
    score = _clamp(0.70 * score + 0.30 * (100.0 * (1.0 - neg_share)))
    return DimensionResult(
        key="complaint_rate",
        score=round(score, 2),
        inputs={
            "n": n,
            "complaint_events": complaint_events,
            "complaint_rate": round(rate, 4),
            "negative_share": round(neg_share, 4),
            "top_complaints": dict(
                sorted(complaints.items(), key=lambda x: -x[1])[:5]
            ),
        },
        formula="0.70*(100-60*complaint_events/n) + 0.30*(100*(1-neg_share))",
        explanation=(
            f"Complaint events/reviews={rate:.2f}, neg_share={neg_share:.2%} → {score:.1f} "
            "(higher is better / fewer complaints)."
        ),
    )


def score_branch_quality(
    *,
    branch_scores: list[float],
    avg_google_rating: float,
    branch_count: int,
) -> DimensionResult:
    if branch_scores:
        mean_b = sum(branch_scores) / len(branch_scores)
        score = _clamp(mean_b)
        src = "mean(branch_intelligence.branch_score)"
    elif branch_count > 0 and avg_google_rating > 0:
        score = _clamp((avg_google_rating / 5.0) * 100.0)
        mean_b = score
        src = "fallback avg google rating"
    else:
        return DimensionResult(
            key="branch_quality",
            score=50.0,
            inputs={"branch_count": branch_count},
            formula="prior 50",
            explanation="No branch quality evidence; prior 50.",
        )
    return DimensionResult(
        key="branch_quality",
        score=round(score, 2),
        inputs={
            "branch_count_scored": len(branch_scores),
            "mean_branch_score": round(mean_b, 2),
            "avg_google_rating": round(float(avg_google_rating or 0), 3),
            "source": src,
        },
        formula="mean(branch_score) or (avg_google_rating/5*100)",
        explanation=f"Branch quality via {src} → {score:.1f} across {len(branch_scores) or branch_count} branches.",
    )
