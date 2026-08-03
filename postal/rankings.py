"""Province and city company rankings."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from postal.scoring import compute_branch_score


def _agg_score(
    *,
    avg_rating: float,
    sentiments: dict[str, int],
    complaints: dict[str, int],
    review_count: int,
    config: dict[str, Any] | None,
) -> float:
    score, _ = compute_branch_score(
        avg_rating=avg_rating,
        sentiments=sentiments,
        complaints=complaints,
        review_count=review_count,
        config=config,
    )
    return score


def build_geo_rankings(
    *,
    branches: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    companies: dict[int, dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Rank companies inside every province and city using local review evidence.
    Score uses the same explainable branch-score formula on the geo subset.
    """
    reviews_by_branch: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for rev in reviews:
        reviews_by_branch[int(rev["branch_id"])].append(rev)

    # geo_level -> geo_key -> company_id -> agg
    province_buckets: dict[str, dict[int, dict[str, Any]]] = defaultdict(
        lambda: defaultdict(lambda: {
            "ratings": [],
            "sentiments": defaultdict(int),
            "complaints": defaultdict(int),
            "branch_ids": set(),
        })
    )
    city_buckets: dict[tuple[str, str], dict[int, dict[str, Any]]] = defaultdict(
        lambda: defaultdict(lambda: {
            "ratings": [],
            "sentiments": defaultdict(int),
            "complaints": defaultdict(int),
            "branch_ids": set(),
        })
    )

    for branch in branches:
        bid = int(branch["id"])
        cid = int(branch["company_id"])
        province = (branch.get("province") or "").strip() or "Unknown"
        city = (branch.get("city") or "").strip() or "Unknown"
        revs = reviews_by_branch.get(bid, [])
        for bucket in (province_buckets[province][cid], city_buckets[(province, city)][cid]):
            bucket["branch_ids"].add(bid)
        if not revs:
            # still count branch presence with google rating if any
            gr = float(branch.get("google_rating") or 0)
            if gr > 0:
                province_buckets[province][cid]["ratings"].append(gr)
                city_buckets[(province, city)][cid]["ratings"].append(gr)
            continue
        for rev in revs:
            rating = float(rev.get("rating") or 0)
            province_buckets[province][cid]["ratings"].append(rating)
            city_buckets[(province, city)][cid]["ratings"].append(rating)
            sent = str(rev.get("sentiment") or "Neutral")
            province_buckets[province][cid]["sentiments"][sent] += 1
            city_buckets[(province, city)][cid]["sentiments"][sent] += 1
            if sent == "Negative":
                cat = str(rev.get("complaint_category") or "other")
                province_buckets[province][cid]["complaints"][cat] += 1
                city_buckets[(province, city)][cid]["complaints"][cat] += 1

    out: list[dict[str, Any]] = []

    def emit(level: str, geo_name: str, province: str, company_map: dict[int, dict[str, Any]]) -> None:
        ranked: list[dict[str, Any]] = []
        for cid, agg in company_map.items():
            company = companies.get(cid)
            if not company:
                continue
            ratings = agg["ratings"]
            review_count = sum(agg["sentiments"].values()) or len(ratings)
            avg_rating = (sum(ratings) / len(ratings)) if ratings else 0.0
            score = _agg_score(
                avg_rating=avg_rating,
                sentiments=dict(agg["sentiments"]),
                complaints=dict(agg["complaints"]),
                review_count=review_count,
                config=config,
            )
            ranked.append(
                {
                    "geo_level": level,
                    "geo_name": geo_name,
                    "province": province,
                    "company_id": cid,
                    "company_name": company["name"],
                    "score": score,
                    "review_count": review_count,
                    "branch_count": len(agg["branch_ids"]),
                    "avg_rating": round(avg_rating, 3),
                    "metrics": {
                        "sentiments": dict(agg["sentiments"]),
                        "complaints": dict(agg["complaints"]),
                    },
                }
            )
        ranked.sort(key=lambda r: (float(r["score"]), int(r["review_count"])), reverse=True)
        for i, row in enumerate(ranked, start=1):
            row["rank"] = i
            out.append(row)

    for province, cmap in province_buckets.items():
        if province == "Unknown" and not any(cmap.values()):
            continue
        emit("province", province, province, cmap)

    for (province, city), cmap in city_buckets.items():
        if city == "Unknown" and province == "Unknown":
            continue
        emit("city", city, province, cmap)

    return out
