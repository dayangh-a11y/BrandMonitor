#!/usr/bin/env python3
"""
Phase 10 — Tipax nationwide discovery (branches only, no review extraction).

Multi-level search: nationwide aliases → province → city → adaptive districts.
Writes discovery coverage + zero-province investigation reports.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from collectors.dedupe import branch_identity_key
from collectors.discovery.engine import (
    NationwideDiscoveryEngine,
    build_zero_province_investigation,
    write_discovery_reports,
)
from collectors.iran_geo import IRAN_PROVINCES, build_discovery_queries
from collectors.sources.registry import build_source
from core.config import load_settings
from core.db import Database
from core.logging_setup import get_logger, setup_logging

log = get_logger("discovery")


async def load_baseline_keys(db: Database, company_name: str) -> set[str]:
    company_id = await db.upsert_company(company_name, source="google_maps")
    rows = await db.list_company_branch_rows(int(company_id))
    keys: set[str] = set()
    for row in rows:
        if int(row.get("is_deleted") or 0):
            continue
        keys.add(
            branch_identity_key(
                place_id=row.get("place_id") or "",
                name=row.get("name") or "",
                address=row.get("address") or "",
            )
        )
    return keys


async def persist_branches(db: Database, company_name: str, branches) -> dict:
    company_id = await db.upsert_company(company_name, source="google_maps")
    inserted = 0
    updated = 0
    existing = {
        branch_identity_key(
            place_id=r.get("place_id") or "",
            name=r.get("name") or "",
            address=r.get("address") or "",
        )
        for r in await db.list_company_branch_rows(int(company_id))
    }
    for branch in branches:
        key = branch_identity_key(
            place_id=branch.place_id,
            name=branch.name,
            address=branch.address,
        )
        await db.upsert_branch(int(company_id), branch)
        if key in existing:
            updated += 1
        else:
            inserted += 1
            existing.add(key)
    active = [
        b
        for b in await db.list_company_branch_rows(int(company_id))
        if not int(b.get("is_deleted") or 0)
    ]
    return {
        "company_id": int(company_id),
        "upserted": len(branches),
        "likely_new": inserted,
        "likely_updated": updated,
        "active_branches_in_db": len(active),
    }


async def main() -> None:
    settings = load_settings()
    setup_logging(settings)
    parser = argparse.ArgumentParser(description="Tipax nationwide discovery engine")
    parser.add_argument("--db", default=os.getenv("DB_PATH", "data/tipax_iran.db"))
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--max-queries", type=int, default=None)
    parser.add_argument("--max-branches-per-query", type=int, default=80)
    parser.add_argument(
        "--city-expand-threshold",
        type=int,
        default=int(os.getenv("CITY_EXPAND_THRESHOLD", "8")),
    )
    parser.add_argument(
        "--preseed-districts",
        action="store_true",
        help="Include mega-city district queries up front (larger budget)",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Print query plan stats and exit (no browser)",
    )
    parser.add_argument(
        "--report-dir",
        default="/opt/cursor/artifacts/phase10_discovery",
    )
    parser.add_argument("--company", default="Tipax")
    args = parser.parse_args()

    os.environ.setdefault("BROWSER_LOCALE", "fa-IR")
    os.environ.setdefault("FAST_DISCOVER", "true")

    plan = build_discovery_queries(
        include_districts=args.preseed_districts,
        include_gap_probes=True,
    )
    by_level: dict[str, int] = {}
    for q in plan:
        by_level[q.level] = by_level.get(q.level, 0) + 1

    if args.plan_only:
        print(
            json.dumps(
                {
                    "queries_planned": len(plan),
                    "by_level": by_level,
                    "provinces": len(IRAN_PROVINCES),
                    "sample": [q.text for q in plan[:25]],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    db = Database(args.db)
    await db.connect()
    baseline = await load_baseline_keys(db, args.company)
    log.info(
        "discovery_start baseline_branches=%s planned_queries=%s by_level=%s",
        len(baseline),
        len(plan),
        by_level,
    )

    source = build_source(
        "google_maps",
        headless=not args.headed and settings.headless,
        max_branches=args.max_branches_per_query,
        max_reviews_per_branch=1,  # unused in discovery-only path
        search_queries=[],
    )
    engine = NationwideDiscoveryEngine(
        source,
        company_name=args.company,
        city_expand_threshold=args.city_expand_threshold,
        include_preseed_districts=args.preseed_districts,
        max_queries=args.max_queries,
    )

    try:
        result = await engine.run(baseline_keys=baseline)
        persist = await persist_branches(db, args.company, result.branches)
        zero_inv = build_zero_province_investigation(result)

        report_dir = Path(args.report_dir)
        paths = write_discovery_reports(
            result, out_dir=report_dir, zero_investigation=zero_inv
        )
        # Mirror into docs/ for the PR
        docs_dir = Path("docs/phase10_discovery")
        write_discovery_reports(result, out_dir=docs_dir, zero_investigation=zero_inv)

        summary = {
            **result.to_report_dict(),
            "persist": persist,
            "report_paths": {k: str(v) for k, v in paths.items()},
        }
        # Drop bulky outcomes from stdout summary duplicate file
        slim = {
            k: v
            for k, v in summary.items()
            if k not in {"query_outcomes", "zero_province_investigation"}
        }
        slim_path = report_dir / "discovery_summary.json"
        slim_path.write_text(json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8")
        Path("docs/phase10_discovery/discovery_summary.json").write_text(
            json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(slim, ensure_ascii=False, indent=2))
        log.info(
            "discovery_finished unique=%s new=%s zero_provinces=%s",
            result.unique_branches,
            result.new_branches_vs_baseline,
            result.zero_provinces,
        )
    finally:
        await source.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
