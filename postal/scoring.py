"""Company-level Postal Intelligence scoring engine (explainable, weighted)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from postal import ALGORITHM_VERSION
from postal.dimensions import (
    DimensionResult,
    score_branch_quality,
    score_complaint_rate,
    score_customer_satisfaction,
    score_delivery_speed,
    score_pricing,
    score_service_coverage,
    score_service_variety,
    score_transparency,
)
from postal.weights import load_scoring_config, normalized_weights


@dataclass
class CompanyScoreBreakdown:
    company_slug: str
    company_name: str
    score: float
    dimensions: dict[str, DimensionResult] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    algorithm_version: str = ALGORITHM_VERSION
    why: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "company_slug": self.company_slug,
            "company_name": self.company_name,
            "score": self.score,
            "algorithm_version": self.algorithm_version,
            "weights": self.weights,
            "dimensions": {
                k: {
                    "score": v.score,
                    "inputs": v.inputs,
                    "formula": v.formula,
                    "explanation": v.explanation,
                }
                for k, v in self.dimensions.items()
            },
            "why": self.why,
            "weighted_contribution": {
                k: round(self.weights[k] * self.dimensions[k].score, 3)
                for k in self.weights
                if k in self.dimensions
            },
        }


def compute_company_score(
    *,
    company_slug: str,
    company_name: str,
    official: dict[str, Any],
    review_stats: dict[str, Any],
    branch_stats: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> CompanyScoreBreakdown:
    """
    Compute 0–100 company score from official profile + review/branch evidence.

    review_stats keys:
      sentiments: dict[str,int], avg_rating, review_count, complaints: dict[str,int]
    branch_stats keys:
      observed_branch_count, avg_google_rating, branch_scores: list[float]
    """
    cfg = config or load_scoring_config()
    weights = normalized_weights(cfg)
    speed_bm = dict(cfg.get("delivery_speed_benchmarks") or {})
    price_bm = dict(cfg.get("pricing_benchmarks") or {})
    cov_bm = dict(cfg.get("coverage_benchmarks") or {})

    delivery = official.get("official_delivery_times") or {}
    pricing = official.get("official_pricing") or {}
    services = list(official.get("services") or [])

    dims: dict[str, DimensionResult] = {}
    dims["customer_satisfaction"] = score_customer_satisfaction(
        sentiments=dict(review_stats.get("sentiments") or {}),
        avg_rating=float(review_stats.get("avg_rating") or 0),
        review_count=int(review_stats.get("review_count") or 0),
    )
    dims["delivery_speed"] = score_delivery_speed(
        intercity_typical_days=float(delivery.get("intercity_typical_days") or 3),
        benchmarks=speed_bm,
    )
    dims["service_coverage"] = score_service_coverage(
        cities=int(official.get("cities_covered_official") or 0),
        provinces=int(official.get("provinces_covered_official") or 0),
        branches=int(official.get("branch_count_official") or 0),
        observed_branches=int(branch_stats.get("observed_branch_count") or 0),
        benchmarks=cov_bm,
    )
    dims["pricing"] = score_pricing(
        price_index=float(pricing.get("price_index") or 1.0),
        benchmarks=price_bm,
    )
    dims["service_variety"] = score_service_variety(services=services)
    dims["transparency"] = score_transparency(
        tracking=dict(official.get("tracking") or {}),
        insurance=dict(official.get("insurance") or {}),
        pricing=pricing,
        working_hours=dict(official.get("working_hours") or {}),
        support=dict(official.get("customer_support") or {}),
        cod=dict(official.get("cod") or {}),
    )
    dims["complaint_rate"] = score_complaint_rate(
        sentiments=dict(review_stats.get("sentiments") or {}),
        complaints=dict(review_stats.get("complaints") or {}),
    )
    dims["branch_quality"] = score_branch_quality(
        branch_scores=list(branch_stats.get("branch_scores") or []),
        avg_google_rating=float(branch_stats.get("avg_google_rating") or 0),
        branch_count=int(branch_stats.get("observed_branch_count") or 0),
    )

    total = 0.0
    why: list[str] = []
    for key, w in weights.items():
        contrib = w * dims[key].score
        total += contrib
        why.append(f"{key}: {dims[key].score:.1f} × w={w:.2f} → {contrib:.2f}")
        why.append(f"  ↳ {dims[key].explanation}")

    score = round(max(0.0, min(100.0, total)), 2)
    why.insert(0, f"Final score {score} = Σ weight_i × dimension_i ({ALGORITHM_VERSION}).")

    return CompanyScoreBreakdown(
        company_slug=company_slug,
        company_name=company_name,
        score=score,
        dimensions=dims,
        weights=weights,
        why=why,
    )


def compute_branch_score(
    *,
    avg_rating: float,
    sentiments: dict[str, int],
    complaints: dict[str, int],
    review_count: int,
    config: dict[str, Any] | None = None,
) -> tuple[float, dict[str, Any]]:
    """Explainable branch score 0–100."""
    cfg = config or load_scoring_config()
    bw = dict(cfg.get("branch_weights") or {})
    w_rating = float(bw.get("rating", 0.35))
    w_sent = float(bw.get("sentiment", 0.30))
    w_comp = float(bw.get("complaint_penalty_scale", 0.20))
    w_vol = float(bw.get("volume_confidence", 0.15))

    rating_s = max(0.0, min(100.0, (float(avg_rating) / 5.0) * 100.0)) if review_count else 50.0
    n = sum(sentiments.values()) or 0
    if n:
        pos = sentiments.get("Positive", 0)
        neu = sentiments.get("Neutral", 0)
        sent_s = 100.0 * (pos + 0.5 * neu) / n
    else:
        sent_s = 50.0
    complaint_events = sum(complaints.values())
    rate = (complaint_events / n) if n else 0.0
    # complaint component: high when few complaints
    comp_s = max(0.0, min(100.0, 100.0 - 55.0 * rate))
    # volume confidence toward observed mix vs prior 50
    kappa = n / (n + float(cfg.get("min_reviews_for_full_confidence", 20)))
    vol_s = 100.0 * kappa

    raw = w_rating * rating_s + w_sent * sent_s + w_comp * comp_s + w_vol * vol_s
    # shrink toward prior when few reviews
    prior = float(cfg.get("prior_score", 50.0))
    score = round(kappa * raw + (1.0 - kappa) * prior, 2)
    score = max(0.0, min(100.0, score))

    explanation = {
        "formula": (
            "kappa*(w_rating*rating_s + w_sent*sent_s + w_comp*comp_s + w_vol*vol_s)"
            " + (1-kappa)*prior"
        ),
        "inputs": {
            "avg_rating": avg_rating,
            "review_count": review_count,
            "sentiments": sentiments,
            "complaints": complaints,
            "rating_s": round(rating_s, 2),
            "sentiment_s": round(sent_s, 2),
            "complaint_s": round(comp_s, 2),
            "volume_s": round(vol_s, 2),
            "kappa": round(kappa, 4),
            "raw": round(raw, 2),
            "prior": prior,
            "weights": {
                "rating": w_rating,
                "sentiment": w_sent,
                "complaint_penalty_scale": w_comp,
                "volume_confidence": w_vol,
            },
        },
        "explanation": (
            f"Branch score {score}: rating_s={rating_s:.1f}, sentiment_s={sent_s:.1f}, "
            f"complaint_s={comp_s:.1f}, volume_s={vol_s:.1f}, kappa={kappa:.2f}."
        ),
    }
    return score, explanation
