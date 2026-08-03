"""Export Postal Intelligence sample tables (JSON/CSV)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from postal.db import PostalIntelligenceDB


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = fieldnames or list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            flat = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v) for k, v in row.items()}
            writer.writerow(flat)


def export_sample_outputs(pi: PostalIntelligenceDB, out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}

    scores = pi.latest_company_scores()
    _write_json(out_dir / "company_scores.json", scores)
    _write_csv(
        out_dir / "company_ranking.csv",
        [
            {
                "rank": i + 1,
                "company": s["name"],
                "slug": s["slug"],
                "score": s["score"],
                "algorithm": s["algorithm_version"],
            }
            for i, s in enumerate(scores)
        ],
    )
    paths["company_scores"] = str(out_dir / "company_scores.json")

    # Official profiles
    official = []
    for c in pi.list_companies():
        off = pi.get_official(int(c["id"]))
        if not off:
            continue
        official.append(
            {
                "slug": c["slug"],
                "name": c["name"],
                "name_fa": c.get("name_fa"),
                "website": c.get("website"),
                "branch_count_official": off.get("branch_count_official"),
                "cities_covered_official": off.get("cities_covered_official"),
                "provinces_covered_official": off.get("provinces_covered_official"),
                "services": json.loads(off.get("services_json") or "[]"),
                "pricing": json.loads(off.get("pricing_json") or "{}"),
                "delivery_times": json.loads(off.get("delivery_times_json") or "{}"),
                "weight_limits": json.loads(off.get("weight_limits_json") or "{}"),
                "size_limits": json.loads(off.get("size_limits_json") or "{}"),
                "support": json.loads(off.get("support_json") or "{}"),
                "working_hours": json.loads(off.get("working_hours_json") or "{}"),
                "insurance": json.loads(off.get("insurance_json") or "{}"),
                "cod": json.loads(off.get("cod_json") or "{}"),
                "tracking": json.loads(off.get("tracking_json") or "{}"),
                "packaging": json.loads(off.get("packaging_json") or "{}"),
                "domestic_services": json.loads(off.get("domestic_services_json") or "[]"),
                "international": json.loads(off.get("international_json") or "{}"),
                "data_quality": off.get("data_quality"),
            }
        )
    _write_json(out_dir / "official_company_dataset.json", official)
    paths["official"] = str(out_dir / "official_company_dataset.json")

    branches = pi.list_branch_intelligence(limit=10000)
    _write_json(out_dir / "branch_intelligence.json", branches[:500])
    _write_csv(
        out_dir / "branch_ranking.csv",
        [
            {
                "rank": i + 1,
                "company": b["company_name"],
                "branch": b["branch_name"],
                "city": b.get("city"),
                "province": b.get("province"),
                "branch_score": b["branch_score"],
                "overall_rating": b["overall_rating"],
                "review_count": b["review_count"],
                "last_activity": b.get("last_activity"),
            }
            for i, b in enumerate(branches[:200])
        ],
    )
    paths["branches"] = str(out_dir / "branch_intelligence.json")

    comparison = pi.latest_comparison("all_companies") or {}
    _write_json(out_dir / "company_comparison.json", comparison)
    if comparison.get("tables"):
        for name, table in comparison["tables"].items():
            _write_csv(out_dir / f"comparison_{name}.csv", table)
    paths["comparison"] = str(out_dir / "company_comparison.json")

    geo = pi.list_geo_rankings()
    _write_json(out_dir / "geo_rankings.json", geo)
    _write_csv(
        out_dir / "province_rankings.csv",
        [g for g in geo if g["geo_level"] == "province"],
        fieldnames=[
            "geo_level", "geo_name", "province", "rank", "company_name",
            "score", "review_count", "branch_count", "avg_rating",
        ],
    )
    _write_csv(
        out_dir / "city_rankings.csv",
        [g for g in geo if g["geo_level"] == "city"],
        fieldnames=[
            "geo_level", "geo_name", "province", "rank", "company_name",
            "score", "review_count", "branch_count", "avg_rating",
        ],
    )
    paths["geo"] = str(out_dir / "geo_rankings.json")

    # Complaint / sentiment rollups
    complaints = []
    sentiments = []
    for c in pi.list_companies():
        stats = pi.company_review_stats(int(c["id"]))
        sentiments.append({"company": c["name"], **(stats.get("sentiments") or {})})
        for cat, n in (stats.get("complaints") or {}).items():
            complaints.append({"company": c["name"], "category": cat, "count": n})
    _write_csv(out_dir / "sentiment_by_company.csv", sentiments)
    _write_csv(out_dir / "complaints_by_company.csv", complaints)
    paths["sentiment"] = str(out_dir / "sentiment_by_company.csv")

    schema_doc = {
        "tables": [
            "pi_companies",
            "pi_official_profiles",
            "pi_branches",
            "pi_reviews",
            "pi_company_scores",
            "pi_branch_intelligence",
            "pi_geo_rankings",
            "pi_comparisons",
            "pi_meta",
        ],
        "notes": "Official profiles are stored separately from reviews (pi_official_profiles).",
    }
    _write_json(out_dir / "schema_overview.json", schema_doc)
    return paths
