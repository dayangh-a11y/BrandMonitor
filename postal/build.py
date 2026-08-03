"""Build Postal Intelligence DB from official profiles + existing review warehouses."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from collectors.phase11.nlp import analyze_review
from postal.branch_intel import build_branch_intelligence
from postal.comparison import build_company_comparison
from postal.db import PostalIntelligenceDB, utcnow
from postal.official import load_official_companies, name_to_slug
from postal.rankings import build_geo_rankings
from postal.scoring import compute_company_score
from postal.weights import load_scoring_config


SOURCE_DBS = (
    ("data/tipax_iran.db", "tipax_iran"),
    ("data/phase11_multisource.db", "phase11"),
    ("data/analytics_demo.db", "analytics_demo"),
)


def _open_ro(path: str) -> sqlite3.Connection | None:
    if not Path(path).exists():
        return None
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def ingest_source_db(
    pi: PostalIntelligenceDB,
    *,
    path: str,
    label: str,
    company_ids: dict[str, int],
) -> dict[str, int]:
    conn = _open_ro(path)
    if conn is None:
        return {"skipped": 1}
    if not _table_exists(conn, "companies") or not _table_exists(conn, "branches"):
        conn.close()
        return {"skipped": 1}

    stats = {"companies": 0, "branches": 0, "reviews": 0}
    src_companies = {
        int(r["id"]): dict(r)
        for r in conn.execute("SELECT * FROM companies")
    }
    branch_map: dict[int, int] = {}  # source branch id -> pi branch id

    for src in conn.execute("SELECT * FROM branches"):
        src = dict(src)
        company = src_companies.get(int(src["company_id"]))
        if not company:
            continue
        slug = name_to_slug(str(company.get("name") or ""))
        if not slug or slug not in company_ids:
            continue
        cid = company_ids[slug]
        bid = pi.upsert_branch(
            cid,
            {
                "name": src.get("name") or "Unknown",
                "address": src.get("address") or "",
                "city": src.get("city") or "",
                "province": src.get("province") or "",
                "latitude": src.get("latitude"),
                "longitude": src.get("longitude"),
                "phone": src.get("phone") or "",
                "maps_url": src.get("maps_url") or "",
                "place_id": src.get("place_id") or "",
                "source_db": label,
                "source_branch_id": int(src["id"]),
                "google_rating": float(src.get("rating") or 0),
                "google_review_count": int(src.get("review_count") or 0),
            },
        )
        branch_map[int(src["id"])] = bid
        stats["branches"] += 1

    if _table_exists(conn, "reviews"):
        batch = 0
        for rev in conn.execute("SELECT * FROM reviews"):
            rev = dict(rev)
            src_bid = int(rev["branch_id"])
            if src_bid not in branch_map:
                continue
            pi_bid = branch_map[src_bid]
            # resolve company_id from pi_branches
            crow = pi.conn.execute(
                "SELECT company_id FROM pi_branches WHERE id=?", (pi_bid,)
            ).fetchone()
            if not crow:
                continue
            text = rev.get("text") or ""
            rating = float(rev.get("rating") or 0)
            nlp = analyze_review(text, rating)
            external_id = rev.get("external_id") or f"{label}-{rev.get('id')}"
            pi.upsert_review(
                pi_bid,
                int(crow["company_id"]),
                {
                    "author": rev.get("author") or "",
                    "rating": rating,
                    "text": text,
                    "published_at": rev.get("published_at") or "",
                    "source": rev.get("source") or "google_maps",
                    "external_id": str(external_id),
                    "sentiment": nlp.sentiment,
                    "complaint_category": nlp.complaint_category,
                    "emotion": nlp.emotion,
                    "urgency": nlp.urgency,
                    "nlp_confidence": int(nlp.confidence_score),
                    "collected_at": rev.get("collected_at") or utcnow(),
                },
            )
            stats["reviews"] += 1
            batch += 1
            if batch % 200 == 0:
                pi.commit()
        pi.commit()

    conn.close()
    return stats


def run_branch_intelligence(pi: PostalIntelligenceDB, config: dict[str, Any]) -> int:
    branches = [dict(r) for r in pi.conn.execute("SELECT * FROM pi_branches")]
    reviews = [dict(r) for r in pi.conn.execute("SELECT * FROM pi_reviews")]
    by_branch: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for rev in reviews:
        by_branch[int(rev["branch_id"])].append(rev)

    n = 0
    for branch in branches:
        payload = build_branch_intelligence(
            branch=branch,
            reviews=by_branch.get(int(branch["id"]), []),
            config=config,
        )
        pi.upsert_branch_intelligence(int(branch["id"]), int(branch["company_id"]), payload)
        n += 1
    return n


def run_company_scores(pi: PostalIntelligenceDB, official_by_slug: dict[str, dict], config: dict[str, Any]) -> list[dict]:
    out = []
    for company in pi.list_companies():
        slug = company["slug"]
        official = official_by_slug[slug]
        review_stats = pi.company_review_stats(int(company["id"]))
        branch_stats = pi.company_branch_stats(int(company["id"]))
        breakdown = compute_company_score(
            company_slug=slug,
            company_name=company["name"],
            official=official,
            review_stats=review_stats,
            branch_stats=branch_stats,
            config=config,
        )
        payload = breakdown.to_dict()
        pi.insert_company_score(int(company["id"]), payload)
        out.append(payload)
    return out


def run_comparison(pi: PostalIntelligenceDB) -> dict[str, Any]:
    companies = pi.list_companies()
    official_rows = {}
    branch_counts = {}
    review_stats = {}
    for c in companies:
        cid = int(c["id"])
        off = pi.get_official(cid)
        if off:
            official_rows[cid] = off
        row = pi.conn.execute(
            "SELECT COUNT(*) n FROM pi_branches WHERE company_id=?", (cid,)
        ).fetchone()
        branch_counts[cid] = int(row["n"])
        review_stats[cid] = pi.company_review_stats(cid)
    scores = pi.latest_company_scores()
    payload = build_company_comparison(
        companies=companies,
        official_rows=official_rows,
        scores=scores,
        branch_counts=branch_counts,
        review_stats=review_stats,
    )
    pi.save_comparison("all_companies", payload)
    return payload


def run_rankings(pi: PostalIntelligenceDB, config: dict[str, Any]) -> int:
    branches = [dict(r) for r in pi.conn.execute("SELECT * FROM pi_branches")]
    reviews = [dict(r) for r in pi.conn.execute("SELECT * FROM pi_reviews")]
    companies = {int(c["id"]): c for c in pi.list_companies()}
    rows = build_geo_rankings(
        branches=branches,
        reviews=reviews,
        companies=companies,
        config=config,
    )
    pi.clear_geo_rankings()
    for row in rows:
        pi.insert_geo_ranking(row)
    pi.commit()
    return len(rows)


def build_postal_intelligence(
    *,
    db_path: str = "data/postal_intelligence.db",
    official_path: str = "config/official_companies.yaml",
    weights_path: str = "config/scoring_weights.yaml",
    source_dbs: tuple[tuple[str, str], ...] = SOURCE_DBS,
) -> dict[str, Any]:
    # Fresh rebuild for deterministic sample outputs
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    if Path(db_path).exists():
        Path(db_path).unlink()

    config = load_scoring_config(weights_path)
    official_list = load_official_companies(official_path)
    official_by_slug = {c["slug"]: c for c in official_list}

    pi = PostalIntelligenceDB(db_path)
    pi.connect()

    company_ids: dict[str, int] = {}
    for official in official_list:
        cid = pi.upsert_company(
            official["slug"],
            official["name"],
            name_fa=official.get("name_fa"),
            website=official.get("website"),
            founded_year=official.get("founded_year"),
            headquarters=official.get("headquarters"),
            ownership=official.get("ownership"),
            description=official.get("description"),
            description_fa=official.get("description_fa"),
        )
        pi.upsert_official_profile(cid, official)
        company_ids[official["slug"]] = cid

    ingest_stats = {}
    for path, label in source_dbs:
        ingest_stats[label] = ingest_source_db(pi, path=path, label=label, company_ids=company_ids)

    n_branches_scored = run_branch_intelligence(pi, config)
    company_scores = run_company_scores(pi, official_by_slug, config)
    comparison = run_comparison(pi)
    n_geo = run_rankings(pi, config)

    summary = {
        "db_path": db_path,
        "algorithm_version": config.get("algorithm_version"),
        "companies": len(company_ids),
        "ingest": ingest_stats,
        "branch_intelligence_rows": n_branches_scored,
        "geo_ranking_rows": n_geo,
        "company_scores": [
            {"name": s["company_name"], "score": s["score"]} for s in company_scores
        ],
        "comparison_top": comparison.get("ranked_by_score") or [],
        "built_at": utcnow(),
    }
    pi.set_meta("last_build", json.dumps(summary, ensure_ascii=False))
    pi.commit()
    pi.close()
    return summary
