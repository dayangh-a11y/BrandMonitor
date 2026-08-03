#!/usr/bin/env python3
"""Regenerate postal_score_v1 audit artifacts WITHOUT changing score values.

Writes (repo root):
  SCORE_METHOD.md is hand-maintained — not overwritten
  SCORE_AUDIT.md is hand-maintained — not overwritten
  WEIGHTS_TABLE.csv
  SCORE_EXPLAINER.json

Also copies CSV/JSON into docs/postal_intelligence/audit/.
"""

from __future__ import annotations

import csv
import json
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from postal.official import load_official_companies
from postal.scoring import compute_company_score
from postal.weights import load_scoring_config, normalized_weights


def dim_confidence(key, inputs, official):
    missing = []
    notes = []
    conf = 1.0
    if key == "customer_satisfaction":
        n = inputs.get("n") or 0
        if n == 0:
            missing.append("reviews")
            conf = 0.20
            notes.append("prior 50 used; no reviews")
        elif n < 30:
            conf = 0.55
            notes.append(f"small sample n={n}")
        elif n < 100:
            conf = 0.75
            notes.append(f"moderate sample n={n}")
        else:
            conf = 0.90
            notes.append(f"large sample n={n}; still subject to Maps selection bias")
        notes.append("sentiment from rule-based NLP, not human labels")
        conf *= 0.95
    elif key == "delivery_speed":
        missing.append("independently_verified_SLA")
        conf = 0.45
        notes.append("curated_v1 official profile, not measured transit data")
    elif key == "service_coverage":
        conf = 0.55
        missing.append("verified_city_list")
        notes.append("cities/provinces/branches_official are curated estimates")
        if inputs.get("branches_observed", 0) == 0:
            missing.append("observed_branches")
            conf -= 0.15
        else:
            conf += 0.10
    elif key == "pricing":
        missing.append("current_public_tariff_table")
        conf = 0.40
        notes.append("price_index is relative curated scalar")
    elif key == "service_variety":
        conf = 0.60
        missing.append("verified_product_catalog")
    elif key == "transparency":
        conf = 0.50
        notes.append("checklist rewards disclosure presence, not accuracy")
        if all((inputs.get("checks") or {}).values()):
            notes.append("saturation: all checks true")
            conf -= 0.10
    elif key == "complaint_rate":
        n = inputs.get("n") or 0
        if n == 0:
            missing.append("reviews")
            conf = 0.20
        else:
            conf = min(0.85, 0.40 + n / 500)
            other = (inputs.get("top_complaints") or {}).get("other", 0)
            if other and inputs.get("complaint_events"):
                share_other = other / max(inputs["complaint_events"], 1)
                if share_other > 0.5:
                    notes.append(f"high other-category share={share_other:.0%}")
                    conf -= 0.10
    elif key == "branch_quality":
        n = inputs.get("branch_count_scored") or 0
        if n == 0:
            missing.append("branch_intelligence")
            conf = 0.20
        else:
            conf = min(0.85, 0.45 + n / 400)
    return round(max(0.05, min(1.0, conf)), 3), missing, notes


COMPONENT_META = {
    "customer_satisfaction": (
        "pi_reviews + rule NLP sentiment/rating",
        "0.60*CSI+0.40*(avg_rating/5*100); prior 50 if n=0",
        "sentiments, avg_rating, n",
        "low–high by n",
        "human labels; non-Maps channels",
        "Maps selection bias; NLP error",
    ),
    "delivery_speed": (
        "official_delivery_times.intercity_typical_days (curated_v1)",
        "linear map days in [1,7] → [100,0]",
        "intercity_typical_days; excellent_days; poor_days",
        "~0.45 low",
        "measured SLA / transit scans",
        "category mismatch; curated optimism",
    ),
    "service_coverage": (
        "official cities/provinces/branches + observed branches",
        "0.40*Sc+0.25*Sp+0.35*Sb vs targets 200/31/400",
        "cities, provinces, branches_official, branches_observed",
        "0.4–0.65",
        "verified city list",
        "caps compress Post; optimistic official counts",
    ),
    "pricing": (
        "official_pricing.price_index curated",
        "linear inverse index [0.7,1.4] → [100,0]",
        "price_index",
        "~0.40 low",
        "live tariff matrices",
        "marketplace dynamics poorly modeled",
    ),
    "service_variety": (
        "official services[] vs 12-item catalog",
        "100*|∩|/12",
        "services list",
        "~0.60",
        "verified catalog depth",
        "equal item weight; cross-category unfairness",
    ),
    "transparency": (
        "official tracking/insurance/pricing/hours/support/cod",
        "100*(#yes)/6 binary checks",
        "six disclosure fields",
        "~0.40–0.50 saturated",
        "accuracy of published info",
        "all companies 100 → constant bias +10",
    ),
    "complaint_rate": (
        "negative review NLP categories + sentiment",
        "0.70*(100-60*rate)+0.30*(100*(1-neg)); prior 50 if n=0",
        "sentiments, complaints",
        "scales with n",
        "official tickets; severity",
        "double count; other-category dump",
    ),
    "branch_quality": (
        "mean pi_branch_intelligence.branch_score",
        "mean(branch_score); fallback rating; prior 50",
        "branch_scores[] or avg_google_rating",
        "scales with branches/reviews",
        "ops QA",
        "prior shrinkage → ~50 mean",
    ),
}


def main() -> int:
    db = ROOT / "data" / "postal_intelligence.db"
    if not db.exists():
        db = ROOT / "docs" / "postal_intelligence" / "postal_intelligence.sample.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    cfg = load_scoring_config()
    weights = normalized_weights(cfg)
    official_by_slug = {o["slug"]: o for o in load_official_companies()}

    companies_out = []
    for row in conn.execute(
        """
        SELECT c.id, c.slug, c.name, c.name_fa, s.score, s.dimensions_json,
               s.explanation_json, s.calculated_at, s.algorithm_version
        FROM pi_companies c
        JOIN pi_company_scores s ON s.id=(
          SELECT id FROM pi_company_scores WHERE company_id=c.id ORDER BY id DESC LIMIT 1)
        ORDER BY s.score DESC
        """
    ):
        dims = json.loads(row["dimensions_json"])
        expl = json.loads(row["explanation_json"])
        official = official_by_slug[row["slug"]]
        cid = row["id"]
        sentiments = {
            r[0]: r[1]
            for r in conn.execute(
                "SELECT sentiment, COUNT(*) FROM pi_reviews WHERE company_id=? GROUP BY sentiment",
                (cid,),
            )
        }
        complaints = {
            r[0]: r[1]
            for r in conn.execute(
                "SELECT complaint_category, COUNT(*) FROM pi_reviews "
                "WHERE company_id=? AND sentiment='Negative' GROUP BY complaint_category",
                (cid,),
            )
        }
        agg = conn.execute(
            "SELECT AVG(rating) a, COUNT(*) n FROM pi_reviews WHERE company_id=?",
            (cid,),
        ).fetchone()
        br = conn.execute(
            "SELECT COUNT(*) n, AVG(google_rating) g FROM pi_branches WHERE company_id=?",
            (cid,),
        ).fetchone()
        scores = [
            float(r[0])
            for r in conn.execute(
                "SELECT branch_score FROM pi_branch_intelligence WHERE company_id=?",
                (cid,),
            )
        ]
        review_stats = {
            "sentiments": sentiments,
            "complaints": complaints,
            "avg_rating": float(agg["a"] or 0),
            "review_count": int(agg["n"] or 0),
        }
        branch_stats = {
            "observed_branch_count": int(br["n"] or 0),
            "avg_google_rating": float(br["g"] or 0),
            "branch_scores": scores,
        }
        recomputed = compute_company_score(
            company_slug=row["slug"],
            company_name=row["name"],
            official=official,
            review_stats=review_stats,
            branch_stats=branch_stats,
            config=cfg,
        )
        match = abs(recomputed.score - float(row["score"])) < 0.011
        dim_audit = {}
        weighted_conf = 0.0
        all_missing = []
        for k, d in dims.items():
            conf, missing, notes = dim_confidence(k, d.get("inputs") or {}, official)
            w = weights[k]
            weighted_conf += w * conf
            all_missing.extend(missing)
            dim_audit[k] = {
                "score": d["score"],
                "weight": w,
                "contribution": round(w * d["score"], 4),
                "formula": d["formula"],
                "inputs": d["inputs"],
                "explanation": d["explanation"],
                "confidence": conf,
                "missing_data": missing,
                "notes": notes,
            }
        overall_conf = round(weighted_conf, 3)
        if review_stats["review_count"] == 0:
            overall_conf = round(overall_conf * 0.7, 3)
        companies_out.append(
            {
                "slug": row["slug"],
                "name": row["name"],
                "name_fa": row["name_fa"],
                "score": row["score"],
                "algorithm_version": row["algorithm_version"],
                "calculated_at": row["calculated_at"],
                "reproducible": match,
                "recomputed_score": recomputed.score,
                "overall_confidence": overall_conf,
                "confidence_interpretation": (
                    "high"
                    if overall_conf >= 0.75
                    else "moderate"
                    if overall_conf >= 0.55
                    else "low"
                    if overall_conf >= 0.35
                    else "very_low"
                ),
                "review_evidence": {
                    "review_count": review_stats["review_count"],
                    "avg_rating": round(review_stats["avg_rating"], 4)
                    if review_stats["review_count"]
                    else None,
                    "sentiments": sentiments,
                    "complaints": complaints,
                },
                "branch_evidence": {
                    "observed_branches": branch_stats["observed_branch_count"],
                    "avg_google_rating": round(branch_stats["avg_google_rating"], 4)
                    if branch_stats["observed_branch_count"]
                    else None,
                    "branch_scores_mean": round(sum(scores) / len(scores), 4) if scores else None,
                },
                "official_data_quality": official.get("data_quality"),
                "missing_data_union": sorted(set(all_missing)),
                "dimensions": dim_audit,
                "weighted_contribution": expl.get("weighted_contribution"),
                "why": expl.get("why"),
            }
        )

    for i, co in enumerate(companies_out, 1):
        co["rank"] = i
        contribs = sorted(co["dimensions"].items(), key=lambda x: -x[1]["contribution"])
        top = contribs[:3]
        bottom = contribs[-2:]
        parts = [
            f"{co['name']} scored {co['score']} under {co['algorithm_version']} (rank #{co['rank']}).",
            f"Overall confidence={co['overall_confidence']} ({co['confidence_interpretation']}).",
            "Largest positive contributions: "
            + ", ".join(f"{k}={v['score']}→{v['contribution']}" for k, v in top)
            + ".",
            "Weakest contributions: "
            + ", ".join(f"{k}={v['score']}→{v['contribution']}" for k, v in bottom)
            + ".",
        ]
        if co["review_evidence"]["review_count"] == 0:
            parts.append(
                "CRITICAL: zero reviews — satisfaction/complaint/branch_quality used priors."
            )
        co["why_narrative"] = " ".join(parts)

    # Load components from existing explainer if present else rebuild minimal
    components_path = ROOT / "SCORE_EXPLAINER.json"
    old_components = []
    if components_path.exists():
        old = json.loads(components_path.read_text(encoding="utf-8"))
        old_components = old.get("components") or []

    explainer = {
        "meta": {
            "algorithm_version": "postal_score_v1",
            "score_values_changed": False,
            "reproducibility_rule": (
                "CompanyScore = round(sum(weight_i * dimension_i), 2) with dimensions from "
                "postal/dimensions.py and weights from config/scoring_weights.yaml"
            ),
            "source_db": str(db),
            "all_companies_reproducible": all(x["reproducible"] for x in companies_out),
            "confidence_model": {
                "description": (
                    "Per-dimension confidence in [0,1]; overall = Σ w_i*conf_i "
                    "(×0.7 if zero reviews). Does NOT alter published scores."
                ),
                "does_not_modify_scores": True,
            },
            "scientific_defensibility": {
                "status": "not_yet_defensible_as_scientific_index",
            },
        },
        "weights": weights,
        "benchmarks": {
            "delivery_speed": cfg["delivery_speed_benchmarks"],
            "pricing": cfg["pricing_benchmarks"],
            "coverage": cfg["coverage_benchmarks"],
            "branch_weights": cfg["branch_weights"],
            "prior_score": cfg["prior_score"],
            "min_reviews_for_full_confidence": cfg["min_reviews_for_full_confidence"],
        },
        "components": old_components,
        "companies": companies_out,
    }

    components_path.write_text(json.dumps(explainer, ensure_ascii=False, indent=2), encoding="utf-8")

    with (ROOT / "WEIGHTS_TABLE.csv").open("w", newline="", encoding="utf-8") as fh:
        fields = [
            "component",
            "weight",
            "data_source",
            "formula",
            "required_input_fields",
            "confidence_level",
            "missing_data",
            "possible_bias",
        ]
        wri = csv.DictWriter(fh, fieldnames=fields)
        wri.writeheader()
        for k, w in weights.items():
            ds, form, req, conf, miss, bias = COMPONENT_META[k]
            wri.writerow(
                {
                    "component": k,
                    "weight": w,
                    "data_source": ds,
                    "formula": form,
                    "required_input_fields": req,
                    "confidence_level": conf,
                    "missing_data": miss,
                    "possible_bias": bias,
                }
            )
        wri.writerow(
            {
                "component": "TOTAL",
                "weight": round(sum(weights.values()), 6),
                "data_source": "",
                "formula": "CompanyScore=round(sum(w_i*D_i),2)",
                "required_input_fields": "",
                "confidence_level": "overall_confidence in SCORE_EXPLAINER.json",
                "missing_data": "",
                "possible_bias": "judgmental weights not empirically calibrated",
            }
        )

    audit_dir = ROOT / "docs" / "postal_intelligence" / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    for name in ("WEIGHTS_TABLE.csv", "SCORE_EXPLAINER.json", "SCORE_METHOD.md", "SCORE_AUDIT.md"):
        src = ROOT / name
        if src.exists():
            shutil.copy(src, audit_dir / name)

    print(
        json.dumps(
            {
                "reproducible": explainer["meta"]["all_companies_reproducible"],
                "score_values_changed": False,
                "companies": [
                    {"name": c["name"], "score": c["score"], "confidence": c["overall_confidence"]}
                    for c in companies_out
                ],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
