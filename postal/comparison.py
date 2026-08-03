"""Automatic company comparison tables."""

from __future__ import annotations

import json
from typing import Any


def _safe_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def build_company_comparison(
    *,
    companies: list[dict[str, Any]],
    official_rows: dict[int, dict[str, Any]],
    scores: list[dict[str, Any]],
    branch_counts: dict[int, int],
    review_stats: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    score_by_id = {int(s["company_id"]): s for s in scores}
    rows: list[dict[str, Any]] = []

    for company in companies:
        cid = int(company["id"])
        off = official_rows.get(cid) or {}
        pricing = _safe_json(off.get("pricing_json"), {})
        delivery = _safe_json(off.get("delivery_times_json"), {})
        services = _safe_json(off.get("services_json"), [])
        intl = _safe_json(off.get("international_json"), {})
        stats = review_stats.get(cid) or {}
        score = score_by_id.get(cid) or {}
        complaints = stats.get("complaints") or {}
        total_c = sum(complaints.values()) or 1
        complaint_dist = {
            k: round(v / total_c, 4)
            for k, v in sorted(complaints.items(), key=lambda x: -x[1])
        }

        rows.append(
            {
                "company_id": cid,
                "slug": company["slug"],
                "name": company["name"],
                "name_fa": company.get("name_fa") or "",
                "score": score.get("score"),
                "prices": {
                    "price_index": pricing.get("price_index"),
                    "base_parcel_0_to_1kg_toman": pricing.get("base_parcel_0_to_1kg_toman"),
                    "extra_kg_toman": pricing.get("extra_kg_toman"),
                },
                "services": {
                    "list": services,
                    "count": len(services),
                    "international": bool((intl or {}).get("enabled")),
                    "cod": bool(_safe_json(off.get("cod_json"), {}).get("available")),
                    "insurance": bool(_safe_json(off.get("insurance_json"), {}).get("available")),
                    "tracking": bool(_safe_json(off.get("tracking_json"), {}).get("available")),
                },
                "coverage": {
                    "cities_official": off.get("cities_covered_official"),
                    "provinces_official": off.get("provinces_covered_official"),
                    "branches_official": off.get("branch_count_official"),
                    "branches_observed": branch_counts.get(cid, 0),
                },
                "delivery_time": {
                    "same_city_days": delivery.get("same_city_days"),
                    "intercity_typical_days": delivery.get("intercity_typical_days"),
                    "remote_typical_days": delivery.get("remote_typical_days"),
                },
                "ratings": {
                    "avg_review_rating": round(float(stats.get("avg_rating") or 0), 3),
                    "review_count": int(stats.get("review_count") or 0),
                    "sentiment": stats.get("sentiments") or {},
                },
                "complaint_distribution": complaint_dist,
                "branch_count": {
                    "official": off.get("branch_count_official"),
                    "observed": branch_counts.get(cid, 0),
                },
            }
        )

    rows.sort(key=lambda r: float(r["score"] or 0), reverse=True)

    tables = {
        "prices": [
            {
                "name": r["name"],
                "price_index": r["prices"]["price_index"],
                "base_1kg_toman": r["prices"]["base_parcel_0_to_1kg_toman"],
                "extra_kg_toman": r["prices"]["extra_kg_toman"],
            }
            for r in rows
        ],
        "services": [
            {
                "name": r["name"],
                "service_count": r["services"]["count"],
                "international": r["services"]["international"],
                "cod": r["services"]["cod"],
                "insurance": r["services"]["insurance"],
                "tracking": r["services"]["tracking"],
            }
            for r in rows
        ],
        "coverage": [
            {
                "name": r["name"],
                "cities": r["coverage"]["cities_official"],
                "provinces": r["coverage"]["provinces_official"],
                "branches_official": r["coverage"]["branches_official"],
                "branches_observed": r["coverage"]["branches_observed"],
            }
            for r in rows
        ],
        "delivery_time": [
            {
                "name": r["name"],
                **r["delivery_time"],
            }
            for r in rows
        ],
        "ratings": [
            {
                "name": r["name"],
                "score": r["score"],
                "avg_review_rating": r["ratings"]["avg_review_rating"],
                "review_count": r["ratings"]["review_count"],
                "sentiment": r["ratings"]["sentiment"],
            }
            for r in rows
        ],
        "complaint_distribution": [
            {
                "name": r["name"],
                "distribution": r["complaint_distribution"],
            }
            for r in rows
        ],
        "branch_count": [
            {
                "name": r["name"],
                "official": r["branch_count"]["official"],
                "observed": r["branch_count"]["observed"],
            }
            for r in rows
        ],
    }

    return {
        "kind": "all_companies",
        "companies": rows,
        "tables": tables,
        "ranked_by_score": [{"rank": i + 1, "name": r["name"], "score": r["score"]} for i, r in enumerate(rows)],
    }
