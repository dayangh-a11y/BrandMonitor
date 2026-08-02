#!/usr/bin/env python3
"""Run a production crawl for one company."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from collectors.crawl_models import CrawlConfig
from collectors.google_maps.production_crawler import (
    GoogleMapsBranchReviewSource,
    ProductionCrawler,
)
from collectors.monitoring import CrawlMonitor
from core.db import Database


async def main() -> None:
    parser = argparse.ArgumentParser(description="BrandMonitor production crawl")
    parser.add_argument("--company", required=True, help="Company/brand search name")
    parser.add_argument("--db", default=os.getenv("DB_PATH", "data/brandmonitor.db"))
    parser.add_argument("--mode", choices=["full", "incremental"], default="incremental")
    parser.add_argument("--max-branches", type=int, default=None)
    parser.add_argument("--max-reviews-per-branch", type=int, default=None)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--resume-run-id", type=int, default=None)
    args = parser.parse_args()

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    db = Database(args.db)
    await db.connect()
    monitor = CrawlMonitor()
    source = GoogleMapsBranchReviewSource(
        headless=not args.headed,
        max_branches=args.max_branches,
        max_reviews_per_branch=args.max_reviews_per_branch,
    )
    crawler = ProductionCrawler(db, source, monitor=monitor)
    config = CrawlConfig(
        company_name=args.company,
        mode=args.mode,
        max_branches=args.max_branches,
        max_reviews_per_branch=args.max_reviews_per_branch,
        max_attempts=args.max_attempts,
        headless=not args.headed,
    )
    try:
        report = await crawler.run(config, run_id=args.resume_run_id)
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        print("monitor:", json.dumps(monitor.health(), ensure_ascii=False))
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
