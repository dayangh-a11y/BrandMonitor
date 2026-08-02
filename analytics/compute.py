from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from analytics.filters import AnalyticsFilter, row_matches


def _parse_day(value: str | None) -> str:
    if not value:
        return ""
    text = str(value)
    if "T" in text:
        return text[:10]
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    return ""


def _bucket(day: str, grain: str) -> str:
    if not day:
        return "unknown"
    if grain == "daily":
        return day
    try:
        dt = datetime.strptime(day[:10], "%Y-%m-%d")
    except ValueError:
        return day
    if grain == "monthly":
        return dt.strftime("%Y-%m")
    # weekly: ISO year-week
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _ranked(counter: Counter[str], *, limit: int = 20) -> list[dict[str, Any]]:
    total = sum(counter.values()) or 1
    return [
        {"name": name, "count": count, "share": round(count / total, 4)}
        for name, count in counter.most_common(limit)
    ]


def _dist_counter(counter: Counter[str]) -> dict[str, int]:
    return dict(counter)


def _csi(sentiments: Counter[str]) -> float:
    """Customer Satisfaction Index: 0–100 from sentiment mix."""
    n = sum(sentiments.values())
    if n == 0:
        return 0.0
    pos = sentiments.get("Positive", 0)
    neu = sentiments.get("Neutral", 0)
    neg = sentiments.get("Negative", 0)
    return round(100.0 * (pos + 0.5 * neu) / n, 2)


def _dimension_breakdown(rows: list[dict], field: str) -> list[dict[str, Any]]:
    c: Counter[str] = Counter()
    for row in rows:
        val = row.get(field)
        if val is None or val == "":
            continue
        if field == "package_damage":
            c["damaged" if val else "ok"] += 1
        else:
            c[str(val)] += 1
    return _ranked(c)


def build_company_dashboard(
    *,
    company: dict[str, Any],
    branches: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    score: dict[str, Any] | None,
    insights: dict[str, Any] | None,
    score_history: list[dict[str, Any]],
    filt: AnalyticsFilter,
) -> dict[str, Any]:
    filtered = [r for r in rows if row_matches(r, filt)]
    if filt.min_review_count is not None:
        # Keep only branches that meet threshold after filter.
        by_branch = Counter(int(r["branch_id"]) for r in filtered)
        allowed = {bid for bid, n in by_branch.items() if n >= filt.min_review_count}
        filtered = [r for r in filtered if int(r["branch_id"]) in allowed]
        branches = [b for b in branches if int(b["id"]) in allowed or not filtered]

    sentiments: Counter[str] = Counter()
    complaints: Counter[str] = Counter()
    positives: Counter[str] = Counter()
    provinces: Counter[str] = Counter()
    cities: Counter[str] = Counter()
    ratings: list[float] = []
    confidences: list[float] = []
    review_trend: Counter[str] = Counter()
    rating_trend_sum: dict[str, float] = defaultdict(float)
    rating_trend_n: dict[str, int] = defaultdict(int)

    for row in filtered:
        sentiments[str(row.get("sentiment") or "Neutral")] += 1
        for cat in row.get("complaint_categories") or []:
            complaints[str(cat)] += 1
        for cat in row.get("positive_categories") or []:
            positives[str(cat)] += 1
        province = (row.get("province") or "Unknown").strip() or "Unknown"
        city = (row.get("city") or "Unknown").strip() or "Unknown"
        provinces[province] += 1
        cities[city] += 1
        rating = float(row.get("review_rating") or 0)
        ratings.append(rating)
        conf = row.get("confidence_overall")
        if conf is not None:
            confidences.append(float(conf))
        day = _parse_day(row.get("event_date"))
        bucket = _bucket(day, filt.trend_grain)
        review_trend[bucket] += 1
        rating_trend_sum[bucket] += rating
        rating_trend_n[bucket] += 1

    branch_scores = []
    for b in branches:
        bid = int(b["id"])
        branch_rows = [r for r in filtered if int(r["branch_id"]) == bid]
        if filt.branch_id is not None and bid != filt.branch_id:
            continue
        branch_scores.append(
            {
                "branch_id": bid,
                "name": b.get("name"),
                "city": b.get("city") or "",
                "province": b.get("province") or "",
                "google_rating": float(b.get("rating") or 0),
                "score": b.get("latest_score"),
                "review_count": len(branch_rows),
            }
        )

    ranked = sorted(
        [x for x in branch_scores if x["score"] is not None],
        key=lambda x: float(x["score"]),
        reverse=True,
    )
    top = ranked[:5]
    lowest = list(reversed(ranked[-5:])) if ranked else []

    score_trend = [
        {
            "date": (h.get("calculated_at") or "")[:10],
            "score": float(h.get("score") or 0),
        }
        for h in score_history
    ]
    rating_trend = [
        {
            "period": k,
            "avg_rating": round(rating_trend_sum[k] / max(rating_trend_n[k], 1), 3),
            "reviews": review_trend[k],
        }
        for k in sorted(review_trend.keys())
    ]
    review_trend_series = [{"period": k, "count": review_trend[k]} for k in sorted(review_trend.keys())]

    overall = float(score["score"]) if score else None
    components = (score or {}).get("components") or {}
    insights = insights or {}
    strengths = list(insights.get("pros") or []) or [c["name"] for c in _ranked(positives, limit=3)]
    improvements = list(insights.get("cons") or []) or [c["name"] for c in _ranked(complaints, limit=3)]

    return {
        "entity_type": "company",
        "company_id": company["id"],
        "company_name": company["name"],
        "filters": filt.to_dict(),
        "overall_score": overall,
        "total_reviews": len(filtered),
        "total_branches": len({int(b["id"]) for b in branches}),
        "average_rating": round(sum(ratings) / len(ratings), 3) if ratings else 0.0,
        "sentiment_distribution": {
            "Positive": sentiments.get("Positive", 0),
            "Neutral": sentiments.get("Neutral", 0),
            "Negative": sentiments.get("Negative", 0),
        },
        "review_trend": review_trend_series,
        "rating_trend": rating_trend,
        "score_trend": score_trend,
        "complaint_categories": _ranked(complaints),
        "positive_categories": _ranked(positives),
        "province_distribution": _ranked(provinces),
        "city_distribution": _ranked(cities),
        "top_performing_branches": top,
        "lowest_performing_branches": lowest,
        "branch_ranking": ranked,
        "ai_executive_summary": insights.get("summary")
        or f"{company['name']}: analytics over {len(filtered)} filtered reviews.",
        "biggest_improvements_needed": improvements[:5],
        "biggest_strengths": strengths[:5],
        "customer_satisfaction_index": _csi(sentiments),
        "confidence_score": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
        "charts": {
            "sentiment_pie": {
                "type": "pie",
                "labels": ["Positive", "Neutral", "Negative"],
                "values": [
                    sentiments.get("Positive", 0),
                    sentiments.get("Neutral", 0),
                    sentiments.get("Negative", 0),
                ],
            },
            "review_trend_line": {
                "type": "line",
                "labels": [x["period"] for x in review_trend_series],
                "values": [x["count"] for x in review_trend_series],
            },
            "rating_trend_line": {
                "type": "line",
                "labels": [x["period"] for x in rating_trend],
                "values": [x["avg_rating"] for x in rating_trend],
            },
            "score_trend_line": {
                "type": "line",
                "labels": [x["date"] for x in score_trend],
                "values": [x["score"] for x in score_trend],
            },
            "complaints_bar": {
                "type": "bar",
                "labels": [x["name"] for x in _ranked(complaints, limit=8)],
                "values": [x["count"] for x in _ranked(complaints, limit=8)],
            },
            "positives_bar": {
                "type": "bar",
                "labels": [x["name"] for x in _ranked(positives, limit=8)],
                "values": [x["count"] for x in _ranked(positives, limit=8)],
            },
            "province_bar": {
                "type": "bar",
                "labels": [x["name"] for x in _ranked(provinces, limit=10)],
                "values": [x["count"] for x in _ranked(provinces, limit=10)],
            },
            "city_heatmap": {
                "type": "heatmap",
                "cells": [
                    {"label": x["name"], "value": x["count"]}
                    for x in _ranked(cities, limit=20)
                ],
            },
            "branch_radar": {
                "type": "radar",
                "labels": [x["name"] for x in ranked[:6]],
                "values": [float(x["score"] or 0) for x in ranked[:6]],
            },
            "branch_score_bar": {
                "type": "bar",
                "labels": [x["name"] for x in ranked[:10]],
                "values": [float(x["score"] or 0) for x in ranked[:10]],
            },
        },
        "score_components": components,
        "computed_from_reviews": len(filtered),
    }


def build_branch_dashboard(
    *,
    branch: dict[str, Any],
    company_name: str,
    rows: list[dict[str, Any]],
    score: dict[str, Any] | None,
    insights: dict[str, Any] | None,
    score_history: list[dict[str, Any]],
    filt: AnalyticsFilter,
) -> dict[str, Any]:
    filtered = [r for r in rows if row_matches(r, filt)]
    sentiments: Counter[str] = Counter()
    complaints: Counter[str] = Counter()
    positives: Counter[str] = Counter()
    staff: Counter[str] = Counter()
    timeline: list[dict[str, Any]] = []
    monthly: Counter[str] = Counter()
    rating_trend_sum: dict[str, float] = defaultdict(float)
    rating_trend_n: dict[str, int] = defaultdict(int)
    confidences: list[float] = []

    for row in filtered:
        sentiments[str(row.get("sentiment") or "Neutral")] += 1
        for cat in row.get("complaint_categories") or []:
            complaints[str(cat)] += 1
        for cat in row.get("positive_categories") or []:
            positives[str(cat)] += 1
        for emp in row.get("mentioned_employees") or []:
            if emp:
                staff[str(emp)] += 1
        day = _parse_day(row.get("event_date"))
        monthly[_bucket(day, "monthly")] += 1
        bucket = _bucket(day, filt.trend_grain)
        rating = float(row.get("review_rating") or 0)
        rating_trend_sum[bucket] += rating
        rating_trend_n[bucket] += 1
        if row.get("confidence_overall") is not None:
            confidences.append(float(row["confidence_overall"]))
        timeline.append(
            {
                "date": day,
                "author": row.get("author") or "",
                "rating": rating,
                "sentiment": row.get("sentiment"),
                "text": (row.get("review_text") or "")[:180],
            }
        )

    timeline.sort(key=lambda x: x.get("date") or "")
    rating_trend = [
        {
            "period": k,
            "avg_rating": round(rating_trend_sum[k] / max(rating_trend_n[k], 1), 3),
            "reviews": rating_trend_n[k],
        }
        for k in sorted(rating_trend_sum.keys())
    ]
    score_trend = [
        {"date": (h.get("calculated_at") or "")[:10], "score": float(h.get("score") or 0)}
        for h in score_history
    ]
    components = (score or {}).get("components") or {}
    insights = insights or {}
    ai_rating = None
    if score is not None:
        # Map 0–100 score onto a 1–5 AI rating scale for executives.
        ai_rating = round(1.0 + 4.0 * (float(score["score"]) / 100.0), 2)

    suggestions = list(insights.get("cons") or [])[:5]
    if not suggestions:
        suggestions = [c["name"] for c in _ranked(complaints, limit=3)]

    historical = score_trend[:]

    return {
        "entity_type": "branch",
        "branch_id": branch["id"],
        "branch_name": branch.get("name"),
        "company_name": company_name,
        "city": branch.get("city") or "",
        "province": branch.get("province") or "",
        "filters": filt.to_dict(),
        "branch_score": float(score["score"]) if score else None,
        "google_rating": float(branch.get("rating") or 0),
        "ai_rating": ai_rating,
        "review_count": len(filtered),
        "rating_trend": rating_trend,
        "score_trend": score_trend,
        "monthly_review_volume": [
            {"period": k, "count": monthly[k]} for k in sorted(monthly.keys())
        ],
        "complaint_breakdown": _ranked(complaints),
        "positive_breakdown": _ranked(positives),
        "review_timeline": timeline[-100:],
        "staff_mentions": _ranked(staff, limit=15),
        "delivery_speed_analysis": _dimension_breakdown(filtered, "delivery_speed"),
        "customer_service_analysis": _dimension_breakdown(filtered, "customer_service"),
        "package_damage_analysis": _dimension_breakdown(filtered, "package_damage"),
        "tracking_quality": _dimension_breakdown(filtered, "tracking"),
        "pricing_analysis": _dimension_breakdown(filtered, "pricing"),
        "professionalism_analysis": _dimension_breakdown(filtered, "professionalism"),
        "ai_branch_summary": insights.get("summary")
        or f"{branch.get('name')}: {len(filtered)} filtered reviews analyzed.",
        "improvement_suggestions": suggestions,
        "historical_changes": historical,
        "sentiment_distribution": _dist_counter(sentiments),
        "customer_satisfaction_index": _csi(sentiments),
        "confidence_score": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
        "score_components": components,
        "charts": {
            "rating_trend_line": {
                "type": "line",
                "labels": [x["period"] for x in rating_trend],
                "values": [x["avg_rating"] for x in rating_trend],
            },
            "score_trend_line": {
                "type": "line",
                "labels": [x["date"] for x in score_trend],
                "values": [x["score"] for x in score_trend],
            },
            "monthly_volume_bar": {
                "type": "bar",
                "labels": [k for k in sorted(monthly.keys())],
                "values": [monthly[k] for k in sorted(monthly.keys())],
            },
            "complaints_bar": {
                "type": "bar",
                "labels": [x["name"] for x in _ranked(complaints, limit=8)],
                "values": [x["count"] for x in _ranked(complaints, limit=8)],
            },
            "positives_bar": {
                "type": "bar",
                "labels": [x["name"] for x in _ranked(positives, limit=8)],
                "values": [x["count"] for x in _ranked(positives, limit=8)],
            },
            "sentiment_pie": {
                "type": "pie",
                "labels": list(sentiments.keys()),
                "values": list(sentiments.values()),
            },
            "delivery_stacked": {
                "type": "stacked_bar",
                "labels": [x["name"] for x in _dimension_breakdown(filtered, "delivery_speed")],
                "values": [x["count"] for x in _dimension_breakdown(filtered, "delivery_speed")],
            },
            "timeline": {
                "type": "timeline",
                "points": [
                    {"date": t["date"], "rating": t["rating"], "sentiment": t["sentiment"]}
                    for t in timeline[-60:]
                ],
            },
            "dimensions_radar": {
                "type": "radar",
                "labels": [
                    "delivery_speed",
                    "customer_service",
                    "tracking",
                    "pricing",
                    "professionalism",
                ],
                "values": [
                    _dimension_score(filtered, "delivery_speed", good=("fast",), bad=("slow",)),
                    _dimension_score(filtered, "customer_service", good=("good",), bad=("bad",)),
                    _dimension_score(filtered, "tracking", good=("good",), bad=("bad",)),
                    _dimension_score(filtered, "pricing", good=("cheap", "fair"), bad=("expensive",)),
                    _dimension_score(filtered, "professionalism", good=("good",), bad=("bad",)),
                ],
            },
        },
    }


def _dimension_score(
    rows: list[dict],
    field: str,
    *,
    good: tuple[str, ...],
    bad: tuple[str, ...],
) -> float:
    vals = [str(r.get(field)) for r in rows if r.get(field) not in (None, "")]
    if not vals:
        return 50.0
    score = 0.0
    for v in vals:
        if v in good:
            score += 100.0
        elif v in bad:
            score += 20.0
        else:
            score += 60.0
    return round(score / len(vals), 2)


def compare_entities(payloads: list[dict[str, Any]], *, label_key: str) -> dict[str, Any]:
    series = []
    for item in payloads:
        series.append(
            {
                "label": item.get(label_key) or item.get("name") or str(item.get("id")),
                "overall_score": item.get("overall_score", item.get("branch_score")),
                "average_rating": item.get("average_rating", item.get("google_rating")),
                "total_reviews": item.get("total_reviews", item.get("review_count")),
                "csi": item.get("customer_satisfaction_index"),
                "sentiment": item.get("sentiment_distribution"),
                "top_complaints": (item.get("complaint_categories") or item.get("complaint_breakdown") or [])[:5],
                "top_positives": (item.get("positive_categories") or item.get("positive_breakdown") or [])[:5],
            }
        )
    return {
        "comparison": series,
        "charts": {
            "score_bar": {
                "type": "bar",
                "labels": [s["label"] for s in series],
                "values": [float(s["overall_score"] or 0) for s in series],
            },
            "csi_bar": {
                "type": "bar",
                "labels": [s["label"] for s in series],
                "values": [float(s["csi"] or 0) for s in series],
            },
            "reviews_bar": {
                "type": "bar",
                "labels": [s["label"] for s in series],
                "values": [int(s["total_reviews"] or 0) for s in series],
            },
        },
    }
