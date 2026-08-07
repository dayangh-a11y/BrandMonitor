"""Phase 11 — geographic analytics payloads (visualization only)."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from analytics.filters import AnalyticsFilter, row_matches
from collectors.iran_geo import IRAN_PROVINCES

# Canonical English labels used by iran_provinces.geojson
_PROVINCE_EN = {p["en"] for p in IRAN_PROVINCES}
_PROVINCE_FA_TO_EN = {p["fa"]: p["en"] for p in IRAN_PROVINCES}

_PROVINCE_ALIASES = {
    "tehran province": "Tehran",
    "tehran": "Tehran",
    "alborz": "Alborz",
    "alborz province": "Alborz",
    "isfahan": "Isfahan",
    "isfahan province": "Isfahan",
    "esfahan": "Isfahan",
    "fars": "Fars",
    "fars province": "Fars",
    "razavi khorasan": "Razavi Khorasan",
    "khorasan razavi": "Razavi Khorasan",
    "east azerbaijan": "East Azerbaijan",
    "east azarbaijan": "East Azerbaijan",
    "west azerbaijan": "West Azerbaijan",
    "west azarbaijan": "West Azerbaijan",
    "ardabil": "Ardabil",
    "ardebil": "Ardabil",
    "yazd": "Yazd",
    "kerman": "Kerman",
    "kermanshah": "Kermanshah",
    "hamadan": "Hamadan",
    "hamedan": "Hamadan",
    "qazvin": "Qazvin",
    "qom": "Qom",
    "markazi": "Markazi",
    "lorestan": "Lorestan",
    "khuzestan": "Khuzestan",
    "bushehr": "Bushehr",
    "hormozgan": "Hormozgan",
    "sistan and baluchestan": "Sistan and Baluchestan",
    "sistan and baluchistan": "Sistan and Baluchestan",
    "kurdistan": "Kurdistan",
    "kordestan": "Kurdistan",
    "ilam": "Ilam",
    "kohgiluyeh and boyer-ahmad": "Kohgiluyeh and Boyer-Ahmad",
    "kohgiluyeh and buyer ahmad": "Kohgiluyeh and Boyer-Ahmad",
    "chaharmahal and bakhtiari": "Chaharmahal and Bakhtiari",
    "chahar mahal and bakhtiari": "Chaharmahal and Bakhtiari",
    "gilan": "Gilan",
    "mazandaran": "Mazandaran",
    "golestan": "Golestan",
    "semnan": "Semnan",
    "zanjan": "Zanjan",
    "north khorasan": "North Khorasan",
    "south khorasan": "South Khorasan",
}


def normalize_province(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return "Unknown"
    if raw in _PROVINCE_EN:
        return raw
    if raw in _PROVINCE_FA_TO_EN:
        return _PROVINCE_FA_TO_EN[raw]
    key = raw.casefold()
    if key in _PROVINCE_ALIASES:
        return _PROVINCE_ALIASES[key]
    # Strip trailing "Province"
    if key.endswith(" province"):
        return normalize_province(raw[: -len(" Province")])
    return raw


def score_color(score: float | None) -> str:
    if score is None:
        return "#94a3b8"
    if score >= 80:
        return "#15803d"  # green
    if score >= 65:
        return "#4ade80"  # light green
    if score >= 50:
        return "#eab308"  # yellow
    if score >= 35:
        return "#f97316"  # orange
    return "#dc2626"  # red


def _review_buckets(counts: list[int]) -> dict[str, Any]:
    edges = [0, 1, 5, 10, 20, 50, 100, 10**9]
    labels = ["0", "1-4", "5-9", "10-19", "20-49", "50-99", "100+"]
    bucket_counts = [0] * len(labels)
    for n in counts:
        for i in range(len(labels)):
            if edges[i] <= n < edges[i + 1]:
                bucket_counts[i] += 1
                break
    return {"labels": labels, "values": bucket_counts}


def _score_buckets(scores: list[float]) -> dict[str, Any]:
    labels = [f"{i}-{i + 9}" for i in range(0, 100, 10)]
    labels[-1] = "90-100"
    values = [0] * 10
    for s in scores:
        idx = min(9, max(0, int(s // 10)))
        if s >= 100:
            idx = 9
        values[idx] += 1
    return {"labels": labels, "values": values}


def build_geo_dashboard(
    *,
    company: dict[str, Any],
    branches: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    insights_by_branch: dict[int, dict[str, Any]],
    filt: AnalyticsFilter,
    provinces_targeted: int = 31,
) -> dict[str, Any]:
    """Compose map pins, heatmaps, histograms, leaderboard, and KPIs."""
    filtered = [r for r in rows if row_matches(r, filt)]
    reviews_by_branch: Counter[int] = Counter(int(r["branch_id"]) for r in filtered)
    complaints_by_branch: dict[int, Counter[str]] = defaultdict(Counter)
    positives_by_branch: dict[int, Counter[str]] = defaultdict(Counter)
    confidence_by_branch: dict[int, list[float]] = defaultdict(list)

    for row in filtered:
        bid = int(row["branch_id"])
        for cat in row.get("complaint_categories") or []:
            complaints_by_branch[bid][str(cat)] += 1
        for cat in row.get("positive_categories") or []:
            positives_by_branch[bid][str(cat)] += 1
        conf = row.get("confidence_overall")
        if conf is not None:
            confidence_by_branch[bid].append(float(conf))

    pins: list[dict[str, Any]] = []
    leaderboard: list[dict[str, Any]] = []
    scored: list[dict[str, Any]] = []

    for branch in branches:
        bid = int(branch["id"])
        if filt.branch_id is not None and bid != filt.branch_id:
            continue
        province = normalize_province(branch.get("province") or "")
        city = (branch.get("city") or "").strip()
        if filt.province and filt.province.lower() not in province.lower() and filt.province.lower() not in (
            branch.get("province") or ""
        ).lower():
            continue
        if filt.city and filt.city.lower() not in city.lower():
            continue

        score_raw = branch.get("latest_score")
        score = float(score_raw) if score_raw is not None else None
        review_count = int(reviews_by_branch.get(bid, 0) or branch.get("review_count") or 0)
        if filt.min_review_count is not None and review_count < filt.min_review_count:
            continue

        google_rating = float(branch.get("rating") or 0)
        confs = confidence_by_branch.get(bid) or []
        confidence = round(sum(confs) / len(confs), 4) if confs else 0.0
        # CSI proxy from branch review sentiments
        sent = Counter(
            str(r.get("sentiment") or "Neutral")
            for r in filtered
            if int(r["branch_id"]) == bid
        )
        n = sum(sent.values())
        csi = (
            round(100.0 * (sent.get("Positive", 0) + 0.5 * sent.get("Neutral", 0)) / n, 2)
            if n
            else 0.0
        )
        insights = insights_by_branch.get(bid) or {}
        top_complaints = [name for name, _ in complaints_by_branch[bid].most_common(5)]
        top_positives = [name for name, _ in positives_by_branch[bid].most_common(5)]
        if not top_complaints:
            top_complaints = list(insights.get("cons") or [])[:5]
        if not top_positives:
            top_positives = list(insights.get("pros") or [])[:5]
        ai_summary = insights.get("summary") or (
            f"{branch.get('name')}: {review_count} reviews, score "
            f"{'n/a' if score is None else round(score, 1)}."
        )

        lat = branch.get("latitude")
        lon = branch.get("longitude")
        try:
            lat_f = float(lat) if lat is not None else None
            lon_f = float(lon) if lon is not None else None
        except (TypeError, ValueError):
            lat_f = lon_f = None

        entry = {
            "branch_id": bid,
            "name": branch.get("name") or "",
            "province": province,
            "city": city,
            "latitude": lat_f,
            "longitude": lon_f,
            "review_count": review_count,
            "score": score,
            "google_rating": google_rating,
            "csi": csi,
            "confidence": confidence,
            "ai_summary": ai_summary,
            "top_complaints": top_complaints,
            "top_positives": top_positives,
            "marker_color": score_color(score),
            "maps_url": branch.get("maps_url") or "",
        }
        if lat_f is not None and lon_f is not None:
            pins.append(entry)
        leaderboard.append(entry)
        if score is not None:
            scored.append(entry)

    ranked = sorted(
        scored,
        key=lambda x: (float(x["score"]), int(x["review_count"])),
        reverse=True,
    )
    # Unscored branches after scored ones by review count
    unscored = sorted(
        [x for x in leaderboard if x["score"] is None],
        key=lambda x: int(x["review_count"]),
        reverse=True,
    )
    full_rank = ranked + unscored
    for i, row in enumerate(full_rank, start=1):
        row["rank"] = i

    top10 = ranked[:10]
    worst10 = list(reversed(ranked[-10:])) if ranked else []

    # Province heatmap rollup
    by_province: dict[str, dict[str, Any]] = {}
    for row in leaderboard:
        prov = row["province"] or "Unknown"
        bucket = by_province.setdefault(
            prov,
            {"province": prov, "branches": 0, "reviews": 0, "score_sum": 0.0, "score_n": 0},
        )
        bucket["branches"] += 1
        bucket["reviews"] += int(row["review_count"] or 0)
        if row["score"] is not None:
            bucket["score_sum"] += float(row["score"])
            bucket["score_n"] += 1

    province_heatmap = []
    for prov in sorted(by_province.keys()):
        b = by_province[prov]
        avg = round(b["score_sum"] / b["score_n"], 2) if b["score_n"] else None
        province_heatmap.append(
            {
                "province": prov,
                "branches": b["branches"],
                "reviews": b["reviews"],
                "average_score": avg,
                "color": score_color(avg),
            }
        )

    # Ensure all 31 provinces appear for choropleth (null = no data)
    present = {p["province"] for p in province_heatmap}
    for p in IRAN_PROVINCES:
        if p["en"] not in present:
            province_heatmap.append(
                {
                    "province": p["en"],
                    "branches": 0,
                    "reviews": 0,
                    "average_score": None,
                    "color": "#334155",
                }
            )

    scores_only = [float(x["score"]) for x in scored]
    review_counts = [int(x["review_count"] or 0) for x in leaderboard]
    google_ratings = [float(x["google_rating"] or 0) for x in leaderboard if x.get("google_rating")]

    provinces_with_branches = sum(1 for p in province_heatmap if p["branches"] > 0 and p["province"] in _PROVINCE_EN)
    coverage_pct = round(100.0 * provinces_with_branches / max(provinces_targeted, 1), 2)

    kpis = {
        "total_branches": len(leaderboard),
        "total_reviews": len(filtered) if filtered else sum(review_counts),
        "average_score": round(sum(scores_only) / len(scores_only), 2) if scores_only else None,
        "highest_score": round(max(scores_only), 2) if scores_only else None,
        "lowest_score": round(min(scores_only), 2) if scores_only else None,
        "average_google_rating": round(sum(google_ratings) / len(google_ratings), 3)
        if google_ratings
        else None,
        "coverage_pct": coverage_pct,
        "provinces_with_branches": provinces_with_branches,
        "provinces_targeted": provinces_targeted,
        "branches_with_coordinates": len(pins),
    }

    return {
        "entity_type": "geo_dashboard",
        "company_id": company["id"],
        "company_name": company["name"],
        "filters": filt.to_dict(),
        "kpis": kpis,
        "map_pins": pins,
        "top10_best": [
            {
                "rank": i,
                "branch": x["name"],
                "branch_id": x["branch_id"],
                "province": x["province"],
                "score": x["score"],
                "review_count": x["review_count"],
            }
            for i, x in enumerate(top10, start=1)
        ],
        "top10_worst": [
            {
                "rank": i,
                "branch": x["name"],
                "branch_id": x["branch_id"],
                "province": x["province"],
                "score": x["score"],
                "review_count": x["review_count"],
            }
            for i, x in enumerate(worst10, start=1)
        ],
        "province_heatmap": province_heatmap,
        "review_distribution": _review_buckets(review_counts),
        "score_distribution": _score_buckets(scores_only),
        "leaderboard": [
            {
                "rank": x["rank"],
                "branch": x["name"],
                "branch_id": x["branch_id"],
                "province": x["province"],
                "city": x["city"],
                "reviews": x["review_count"],
                "google_rating": x["google_rating"],
                "ai_score": x["score"],
                "csi": x["csi"],
                "confidence": x["confidence"],
            }
            for x in full_rank
        ],
        "charts": {
            "top10_best_bar": {
                "type": "bar",
                "orientation": "h",
                "labels": [x["name"] for x in reversed(top10)],
                "values": [float(x["score"] or 0) for x in reversed(top10)],
                "extra": {
                    "province": [x["province"] for x in reversed(top10)],
                    "reviews": [x["review_count"] for x in reversed(top10)],
                },
            },
            "top10_worst_bar": {
                "type": "bar",
                "orientation": "h",
                "labels": [x["name"] for x in reversed(worst10)],
                "values": [float(x["score"] or 0) for x in reversed(worst10)],
                "extra": {
                    "province": [x["province"] for x in reversed(worst10)],
                    "reviews": [x["review_count"] for x in reversed(worst10)],
                },
            },
            "review_histogram": {
                "type": "bar",
                **_review_buckets(review_counts),
            },
            "score_histogram": {
                "type": "bar",
                **_score_buckets(scores_only),
            },
        },
        "computed_from_reviews": len(filtered),
    }
