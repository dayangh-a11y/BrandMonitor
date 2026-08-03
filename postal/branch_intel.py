"""Branch intelligence aggregations."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from postal import ALGORITHM_VERSION
from postal.scoring import compute_branch_score


def _month(value: str) -> str:
    text = (value or "").strip()
    if len(text) >= 7 and text[4] == "-":
        return text[:7]
    return "unknown"


def build_branch_intelligence(
    *,
    branch: dict[str, Any],
    reviews: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sentiments: Counter[str] = Counter()
    complaints: Counter[str] = Counter()
    trend: Counter[str] = Counter()
    ratings: list[float] = []
    last_activity = ""

    for rev in reviews:
        sentiments[str(rev.get("sentiment") or "Neutral")] += 1
        cat = str(rev.get("complaint_category") or "other")
        if str(rev.get("sentiment")) == "Negative":
            complaints[cat] += 1
        published = str(rev.get("published_at") or rev.get("collected_at") or "")
        trend[_month(published)] += 1
        if published > last_activity:
            last_activity = published
        ratings.append(float(rev.get("rating") or 0))

    review_count = len(reviews)
    if ratings:
        overall_rating = sum(ratings) / len(ratings)
    else:
        overall_rating = float(branch.get("google_rating") or 0)

    score, explanation = compute_branch_score(
        avg_rating=overall_rating,
        sentiments=dict(sentiments),
        complaints=dict(complaints),
        review_count=review_count,
        config=config,
    )

    trend_rows = [
        {"month": month, "count": count}
        for month, count in sorted(trend.items())
        if month != "unknown" or count
    ]

    return {
        "overall_rating": round(overall_rating, 3),
        "review_count": review_count,
        "complaint_categories": dict(complaints),
        "sentiment": dict(sentiments),
        "review_trend": trend_rows,
        "last_activity": last_activity,
        "branch_score": score,
        "explanation": explanation,
        "algorithm_version": ALGORITHM_VERSION,
    }


def group_reviews_by_branch(reviews: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for rev in reviews:
        grouped[int(rev["branch_id"])].append(rev)
    return grouped
