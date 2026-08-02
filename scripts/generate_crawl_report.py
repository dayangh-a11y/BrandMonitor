#!/usr/bin/env python3
"""Generate / print a crawl report for a run id."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from collectors.google_maps.production_crawler import ProductionCrawler
from collectors.monitoring import CrawlMonitor
from core.db import Database


class _NoopSource:
    async def discover_branches(self, company_name: str):
        return []

    async def collect_reviews(self, branch):
        return []

    async def close(self) -> None:
        return None


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--db", default=os.getenv("DB_PATH", "data/brandmonitor.db"))
    parser.add_argument("--out", default=None, help="Optional JSON output path")
    args = parser.parse_args()

    db = Database(args.db)
    await db.connect()
    try:
        existing = await db.get_crawl_report(args.run_id)
        if existing is None:
            crawler = ProductionCrawler(db, _NoopSource(), monitor=CrawlMonitor())
            report = await crawler.build_report(args.run_id)
            payload = report.to_dict()
            await db.save_crawl_report(args.run_id, payload)
        else:
            payload = existing

        text = json.dumps(payload, ensure_ascii=False, indent=2)
        print(text)
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"wrote {args.out}")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
