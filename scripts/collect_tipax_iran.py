#!/usr/bin/env python3
"""
Collect Tipax branches across all Iran provinces from Google Maps.

- Full metadata (phone, coords, city/province, Maps URL)
- All available reviews + owner replies
- Incremental: re-runs only persist new/edited reviews
- Writes a coverage report JSON
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from collectors.crawl_models import CrawlConfig
from collectors.google_maps.production_crawler import ProductionCrawler
from collectors.iran_geo import IRAN_PROVINCES, tipax_search_queries
from collectors.monitoring import CrawlMonitor
from collectors.sources.registry import build_source
from core.config import load_settings
from core.db import Database
from core.logging_setup import get_logger, setup_logging

log = get_logger("crawler")


async def build_coverage_report(db: Database, run_id: int) -> dict:
    run = await db.get_crawl_run(run_id)
    tasks = await db.list_crawl_branch_tasks(run_id)
    stats = await db.get_crawl_stats(run_id)
    company_id = await db.upsert_company("Tipax", source="google_maps")
    branches = await db.list_company_branch_rows(int(company_id))
    active_branches = [b for b in branches if not int(b.get("is_deleted") or 0)]

    # Review totals for Tipax
    assert db._conn is not None
    cur = await db._conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM reviews r
        JOIN branches b ON b.id = r.branch_id
        WHERE b.company_id = ? AND COALESCE(r.is_deleted, 0) = 0
        """,
        (company_id,),
    )
    total_reviews = int((await cur.fetchone())["c"])

    cur = await db._conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM reviews r
        JOIN branches b ON b.id = r.branch_id
        WHERE b.company_id = ?
          AND COALESCE(r.is_deleted, 0) = 0
          AND TRIM(COALESCE(r.owner_response, '')) != ''
        """,
        (company_id,),
    )
    reviews_with_owner_reply = int((await cur.fetchone())["c"])

    cur = await db._conn.execute(
        """
        SELECT
            SUM(CASE WHEN TRIM(COALESCE(phone,'')) != '' THEN 1 ELSE 0 END) AS with_phone,
            SUM(CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN 1 ELSE 0 END) AS with_coords,
            SUM(CASE WHEN TRIM(COALESCE(maps_url,'')) != '' THEN 1 ELSE 0 END) AS with_url,
            SUM(CASE WHEN TRIM(COALESCE(province,'')) != '' THEN 1 ELSE 0 END) AS with_province
        FROM branches
        WHERE company_id = ? AND COALESCE(is_deleted, 0) = 0
        """,
        (company_id,),
    )
    meta = dict(await cur.fetchone())

    discovered = int(stats.get("branches_discovered", len(tasks)))
    completed = sum(1 for t in tasks if t.get("status") == "succeeded")
    failed = sum(1 for t in tasks if t.get("status") == "failed")
    pending = sum(1 for t in tasks if t.get("status") in {"pending", "running"})
    duplicates_skipped = int(stats.get("duplicates_skipped", 0))
    reviews_found = int(stats.get("reviews_found", 0))
    reviews_new = int(stats.get("reviews_new", 0))
    reviews_updated = int(stats.get("reviews_updated", 0))

    # Estimated coverage vs provinces searched (31) and discovered task completion.
    provinces_targeted = len(IRAN_PROVINCES)
    province_hits: dict[str, int] = {}
    known_province_labels = {
        p["fa"].casefold() for p in IRAN_PROVINCES
    } | {p["en"].casefold() for p in IRAN_PROVINCES}
    matched_known_provinces: set[str] = set()
    for b in active_branches:
        prov = (b.get("province") or "Unknown").strip() or "Unknown"
        province_hits[prov] = province_hits.get(prov, 0) + 1
        key = prov.casefold()
        for province in IRAN_PROVINCES:
            if key in {province["fa"].casefold(), province["en"].casefold()} or key in province[
                "en"
            ].casefold():
                matched_known_provinces.add(province["en"])
                break
            if province["fa"] in prov or province["en"].casefold() in key:
                matched_known_provinces.add(province["en"])
                break

    completion_rate = (completed / discovered) if discovered else 0.0
    # Heuristic: Tipax public footprint is large; coverage ≈ discovery completeness
    # weighted by branch task success and known-province presence.
    province_presence = len(matched_known_provinces)
    geo_coverage = min(1.0, province_presence / provinces_targeted) if provinces_targeted else 0.0
    estimated_coverage = round(min(1.0, 0.6 * completion_rate + 0.4 * geo_coverage), 4)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "company": "Tipax",
        "run_id": run_id,
        "mode": (run or {}).get("mode"),
        "status": (run or {}).get("status"),
        "total_branches_discovered": discovered,
        "completed_branches": completed,
        "failed_branches": failed,
        "pending_branches": pending,
        "total_reviews": total_reviews,
        "reviews_found_this_run": reviews_found,
        "reviews_new": reviews_new,
        "reviews_updated": reviews_updated,
        "duplicates_skipped": duplicates_skipped,
        "reviews_with_owner_reply": reviews_with_owner_reply,
        "active_branches_in_db": len(active_branches),
        "metadata_coverage": {
            "with_phone": int(meta.get("with_phone") or 0),
            "with_coordinates": int(meta.get("with_coords") or 0),
            "with_maps_url": int(meta.get("with_url") or 0),
            "with_province": int(meta.get("with_province") or 0),
        },
        "provinces_targeted": provinces_targeted,
        "provinces_with_branches": province_presence,
        "branches_by_province": dict(sorted(province_hits.items(), key=lambda x: (-x[1], x[0]))),
        "estimated_coverage": estimated_coverage,
        "estimated_coverage_note": (
            "0.6*branch_completion + 0.4*(provinces_with_branches/31). "
            "Google limited-view may reduce review yield."
        ),
        "incremental": {
            "supported": True,
            "unchanged_reviews_skipped_as_duplicates": duplicates_skipped,
        },
    }


async def main() -> None:
    settings = load_settings()
    setup_logging(settings)
    parser = argparse.ArgumentParser(description="Tipax Iran-wide Google Maps collector")
    parser.add_argument("--db", default=os.getenv("DB_PATH", "data/tipax_iran.db"))
    parser.add_argument("--mode", default="incremental", choices=["incremental", "full"])
    parser.add_argument("--max-branches", type=int, default=None)
    parser.add_argument("--max-reviews-per-branch", type=int, default=5000)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--queries-limit",
        type=int,
        default=None,
        help="Optional cap on province queries (debug)",
    )
    parser.add_argument(
        "--report-out",
        default="/opt/cursor/artifacts/tipax_iran_coverage_report.json",
    )
    parser.add_argument("--brand-query", default="تیپاکس")
    args = parser.parse_args()

    os.environ.setdefault("BROWSER_LOCALE", "fa-IR")
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)

    queries = tipax_search_queries(args.brand_query)
    if args.queries_limit is not None:
        queries = queries[: max(1, args.queries_limit)]

    db = Database(args.db)
    await db.connect()
    source = build_source(
        "google_maps",
        headless=not args.headed and settings.headless,
        max_branches=args.max_branches,
        max_reviews_per_branch=args.max_reviews_per_branch,
        search_queries=queries,
    )
    crawler = ProductionCrawler(db, source, monitor=CrawlMonitor())
    config = CrawlConfig(
        company_name="Tipax",
        mode=args.mode,  # type: ignore[arg-type]
        max_attempts=settings.crawl_max_attempts,
        headless=not args.headed and settings.headless,
        max_branches=args.max_branches,
        max_reviews_per_branch=args.max_reviews_per_branch,
        detect_deleted_reviews=True,
        # Multi-province discovery can miss some results; do not tombstone.
        detect_deleted_branches=False,
    )

    log.info(
        "tipax_iran_crawl_start queries=%s mode=%s db=%s",
        len(queries),
        args.mode,
        args.db,
    )
    try:
        report = await crawler.run(config)
        coverage = await build_coverage_report(db, report.run_id)
        coverage["crawl_report"] = report.to_dict()
        coverage["search_queries_used"] = len(queries)
        out = Path(args.report_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")
        # Also store under data/
        Path("data/tipax_iran_coverage_report.json").write_text(
            json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(coverage, ensure_ascii=False, indent=2))
        log.info("tipax_iran_coverage_written path=%s", out)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
