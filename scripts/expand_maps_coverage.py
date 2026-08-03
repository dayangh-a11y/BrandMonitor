#!/usr/bin/env python3
"""Expand Google Maps branch + review coverage for supported postal companies.

Uses province/city queries + brand-name relevance filters to reduce junk hits.
Does not modify postal_score_v1.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collectors.crawl_models import CrawlConfig
from collectors.google_maps.production_crawler import (
    GoogleMapsBranchReviewSource,
    ProductionCrawler,
)
from collectors.iran_geo import IRAN_PROVINCES
from collectors.monitoring import CrawlMonitor
from core.config import load_settings
from core.db import Database
from core.logging_setup import get_logger, setup_logging
from models.branch import Branch

log = get_logger("coverage_expand")

BRANDS = [
    {
        "name": "Pishro",
        "query": "پست پیشرو",
        "include": [r"پیشرو", r"pishro"],
        "exclude": [r"تیپاکس", r"tipax", r"چاپار", r"ماهکس", r"الوپیک", r"شرکت ملی پست"],
    },
    {
        "name": "Post",
        "query": "شرکت ملی پست",
        "include": [r"پست", r"post"],
        "exclude": [r"تیپاکس", r"tipax", r"چاپار", r"ماهکس", r"الوپیک", r"پیشرو", r"pishro", r"alopeyk"],
    },
    {
        "name": "AloPeyk",
        "query": "الوپیک",
        "include": [r"الوپیک", r"alo.?peyk", r"alopeyk"],
        "exclude": [r"تیپاکس", r"چاپار", r"ماهکس"],
    },
    {
        "name": "Mahex",
        "query": "ماهکس",
        "include": [r"ماهکس", r"mahex"],
        "exclude": [r"تیپاکس", r"چاپار", r"الوپیک"],
    },
    {
        "name": "Chapar",
        "query": "چاپار",
        "include": [r"چاپار", r"chapar"],
        "exclude": [r"تیپاکس", r"ماهکس", r"الوپیک"],
    },
    {
        "name": "Tipax",
        "query": "تیپاکس",
        "include": [r"تیپاکس", r"tipax"],
        "exclude": [r"چاپار", r"ماهکس", r"الوپیک"],
    },
]

MAJOR_CITIES_FA = [
    "تهران", "کرج", "اصفهان", "شیراز", "مشهد", "تبریز", "اهواز", "رشت",
    "کرمان", "یزد", "قم", "همدان", "کرمانشاه", "ارومیه", "ساری", "اراک",
]


def brand_queries(brand_query: str, *, provinces: int = 20) -> list[str]:
    q = brand_query.strip()
    out = [q, f"نمایندگی {q}", f"شعبه {q}"]
    for province in IRAN_PROVINCES[: max(0, provinces)]:
        out.append(f"{q} {province['fa']}")
    for city in MAJOR_CITIES_FA[:12]:
        out.append(f"{q} {city}")
    seen: set[str] = set()
    uniq = []
    for item in out:
        k = item.casefold()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(item)
    return uniq


def relevant(branch: Branch, include: list[str], exclude: list[str]) -> bool:
    blob = f"{branch.name} {branch.address}".casefold()
    if any(re.search(ex, blob, re.I) for ex in exclude):
        return False
    return any(re.search(inc, blob, re.I) for inc in include)


class FilteredMapsSource:
    """Wraps GoogleMapsBranchReviewSource with brand-name filters."""

    def __init__(self, inner: GoogleMapsBranchReviewSource, include: list[str], exclude: list[str]):
        self.inner = inner
        self.include = include
        self.exclude = exclude

    async def discover_branches(self, company_name: str) -> list[Branch]:
        found = await self.inner.discover_branches(company_name)
        kept = [b for b in found if relevant(b, self.include, self.exclude)]
        log.info(
            "maps_filter company=%s found=%s kept=%s",
            company_name,
            len(found),
            len(kept),
        )
        return kept

    async def collect_reviews(self, branch: Branch):
        return await self.inner.collect_reviews(branch)

    async def close(self) -> None:
        await self.inner.close()


async def collect_brand(
    *,
    brand: dict,
    db_path: str,
    max_branches: int | None,
    max_reviews_per_branch: int | None,
    provinces: int,
    headless: bool,
) -> dict:
    settings = load_settings()
    setup_logging(settings)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path)
    await db.connect()
    monitor = CrawlMonitor()
    queries = brand_queries(brand["query"], provinces=provinces)
    log.info("coverage_queries brand=%s n=%s", brand["name"], len(queries))
    inner = GoogleMapsBranchReviewSource(
        headless=headless,
        max_branches=max_branches,
        max_reviews_per_branch=max_reviews_per_branch,
        search_queries=queries,
    )
    source = FilteredMapsSource(inner, brand["include"], brand["exclude"])
    crawler = ProductionCrawler(db, source, monitor=monitor)
    config = CrawlConfig(
        company_name=brand["name"],
        mode="full",
        max_branches=max_branches,
        max_reviews_per_branch=max_reviews_per_branch,
        max_attempts=2,
        headless=headless,
    )
    try:
        report = await crawler.run(config)
        payload = report.to_dict()
        payload["brand"] = brand["name"]
        payload["db"] = db_path
        payload["queries"] = len(queries)
        payload["monitor"] = monitor.health()
        return payload
    finally:
        await source.close()
        await db.close()


async def main_async(args: argparse.Namespace) -> dict:
    brands = BRANDS
    if args.company:
        wanted = [c.strip().lower() for c in args.company.split(",") if c.strip()]
        by_name = {b["name"].lower(): b for b in brands}
        brands = [by_name[name] for name in wanted if name in by_name]

    results = []
    for brand in brands:
        db_path = str(Path(args.out_dir) / f"{brand['name'].lower()}_coverage.db")
        # fresh DB for clean filtered collection
        if Path(db_path).exists() and args.fresh:
            Path(db_path).unlink()
        log.info("coverage_collect_start brand=%s db=%s", brand["name"], db_path)
        try:
            result = await collect_brand(
                brand=brand,
                db_path=db_path,
                max_branches=args.max_branches,
                max_reviews_per_branch=args.max_reviews_per_branch,
                provinces=args.provinces,
                headless=not args.headed,
            )
            results.append(result)
            log.info("coverage_collect_done brand=%s", brand["name"])
        except Exception as exc:  # noqa: BLE001
            log.exception("coverage_collect_failed brand=%s", brand["name"])
            results.append({"brand": brand["name"], "error": str(exc), "db": db_path})
    summary = {"results": results}
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    (Path(args.out_dir) / "maps_expand_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="data/coverage_expand")
    parser.add_argument("--company", default="", help="Comma-separated brand names (order preserved)")
    parser.add_argument("--max-branches", type=int, default=30)
    parser.add_argument("--max-reviews-per-branch", type=int, default=30)
    parser.add_argument("--provinces", type=int, default=20)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    summary = asyncio.run(main_async(args))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
