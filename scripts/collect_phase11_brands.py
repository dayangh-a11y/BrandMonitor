#!/usr/bin/env python3
"""
Phase 11 — bounded multi-brand Google Maps collection (quality-focused).

Collects Chapar / Post / Mahex / AloPeyk into data/phase11_multisource.db
using major-city queries (not full nationwide expansion).

Other sources (Balad, Neshan, news, complaint sites) are registered as
extensible stubs — rows would carry review_source accordingly when adapters land.
Does not modify review-extraction internals beyond calling existing collector APIs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from collectors.crawl_models import CrawlConfig
from collectors.google_maps.production_crawler import ProductionCrawler
from collectors.iran_geo import IRAN_PROVINCES
from collectors.monitoring import CrawlMonitor
from collectors.sources.registry import build_source
from core.config import load_settings
from core.db import Database
from core.logging_setup import get_logger, setup_logging

log = get_logger("phase11")

BRANDS = [
    {"name": "Chapar", "query": "چاپار"},
    {"name": "Post", "query": "پست ایران"},
    {"name": "Mahex", "query": "ماهکس"},
    {"name": "AloPeyk", "query": "الوپیک"},
]

# Quality-first geo sample (cap runtime): capitals + a few dense metros
MAJOR_CITIES_FA = [
    "تهران",
    "کرج",
    "اصفهان",
    "شیراز",
    "مشهد",
    "تبریز",
    "اهواز",
    "رشت",
    "کرمان",
    "یزد",
    "قم",
    "همدان",
]


def brand_queries(brand_query: str, *, provinces: int = 8) -> list[str]:
    q = (brand_query or "").strip()
    out = [q, f"{q} ایران", f"نمایندگی {q}"]
    for city in MAJOR_CITIES_FA:
        out.append(f"{q} {city}")
    for province in IRAN_PROVINCES[: max(0, provinces)]:
        out.append(f"{q} {province['fa']}")
    # dedupe
    seen: set[str] = set()
    uniq = []
    for item in out:
        k = item.casefold()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(item)
    return uniq


async def collect_brand(
    *,
    db: Database,
    settings,
    brand: dict,
    max_branches: int | None,
    max_reviews: int,
    headed: bool,
    provinces: int,
    queries_limit: int | None,
) -> dict:
    queries = brand_queries(brand["query"], provinces=provinces)
    if queries_limit is not None:
        queries = queries[: max(1, queries_limit)]
    source = build_source(
        "google_maps",
        headless=not headed and settings.headless,
        max_branches=max_branches,
        max_reviews_per_branch=max_reviews,
        search_queries=queries,
    )
    crawler = ProductionCrawler(db, source, monitor=CrawlMonitor())
    config = CrawlConfig(
        company_name=brand["name"],
        mode="incremental",
        max_attempts=settings.crawl_max_attempts,
        headless=not headed and settings.headless,
        max_branches=max_branches,
        max_reviews_per_branch=max_reviews,
        detect_deleted_reviews=True,
        detect_deleted_branches=False,
    )
    log.info(
        "phase11_brand_start brand=%s queries=%s max_branches=%s max_reviews=%s",
        brand["name"],
        len(queries),
        max_branches,
        max_reviews,
    )
    try:
        report = await crawler.run(config)
        return {
            "brand": brand["name"],
            "queries": len(queries),
            "report": report.to_dict(),
        }
    finally:
        await source.close()


async def main() -> None:
    settings = load_settings()
    setup_logging(settings)
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/phase11_multisource.db")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--max-branches", type=int, default=25)
    parser.add_argument("--max-reviews-per-branch", type=int, default=15)
    parser.add_argument("--provinces", type=int, default=6)
    parser.add_argument("--queries-limit", type=int, default=None)
    parser.add_argument(
        "--brands",
        nargs="*",
        default=[b["name"] for b in BRANDS],
    )
    parser.add_argument(
        "--report-out",
        default="/opt/cursor/artifacts/phase11_collection_report.json",
    )
    args = parser.parse_args()

    os.environ.setdefault("BROWSER_LOCALE", "fa-IR")
    os.environ.setdefault("FAST_DISCOVER", "true")
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)

    selected = [b for b in BRANDS if b["name"] in set(args.brands)]
    db = Database(args.db)
    await db.connect()
    results = []
    try:
        for brand in selected:
            # Fresh source/browser per brand
            results.append(
                await collect_brand(
                    db=db,
                    settings=settings,
                    brand=brand,
                    max_branches=args.max_branches,
                    max_reviews=args.max_reviews_per_branch,
                    headed=args.headed,
                    provinces=args.provinces,
                    queries_limit=args.queries_limit,
                )
            )
    finally:
        await db.close()

    payload = {
        "db": args.db,
        "brands": results,
        "note": (
            "Google Maps only in this run. Balad/Neshan/news/complaint adapters "
            "are planned stubs — review_source remains google_maps."
        ),
    }
    out = Path(args.report_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
