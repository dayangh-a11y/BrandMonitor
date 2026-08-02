#!/usr/bin/env python3
"""Manual / scheduled / retry crawl runner with config-driven companies."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from collectors.company_config import list_enabled_companies, load_company_config
from collectors.crawl_models import CrawlConfig
from collectors.google_maps.production_crawler import ProductionCrawler
from collectors.monitoring import CrawlMonitor
from collectors.scheduler import CrawlScheduler, ScheduleSpec
from collectors.sources.registry import build_source, build_source_for_company
from core.config import load_settings
from core.db import Database
from core.logging_setup import get_logger, setup_logging
from core.metrics import METRICS, flush_metrics_to_db

log = get_logger("scheduler")


async def _run_crawl(
    db: Database,
    spec: ScheduleSpec,
    *,
    headed: bool = False,
    max_branches: int | None = None,
    max_reviews: int | None = None,
    branch_place_id: str | None = None,
    branch_name: str | None = None,
    source_id: str = "google_maps",
) -> dict:
    settings = load_settings()
    monitor = CrawlMonitor()
    source = build_source(
        source_id,
        headless=not headed and settings.headless,
        max_branches=max_branches,
        max_reviews_per_branch=max_reviews,
    )
    crawler = ProductionCrawler(db, source, monitor=monitor)
    config = CrawlConfig(
        company_name=spec.company_name,
        mode=spec.mode,  # type: ignore[arg-type]
        max_attempts=settings.crawl_max_attempts,
        headless=not headed and settings.headless,
        max_branches=max_branches,
        max_reviews_per_branch=max_reviews,
        branch_place_id=branch_place_id,
        branch_name=branch_name,
    )
    report = await crawler.run(config)
    METRICS.record_crawl(
        reviews_found=report.reviews_found,
        reviews_new=report.reviews_new,
        reviews_updated=report.reviews_updated,
        duration_seconds=report.duration_seconds or 0.0,
        failed_branches=report.branches_failed,
        branches=report.branches_succeeded + report.branches_failed,
    )
    try:
        await flush_metrics_to_db(db)
    except Exception as exc:  # noqa: BLE001 — metrics must not fail crawl
        log.warning("metrics_flush_failed error=%s", exc)
    log.info(
        "crawl_finished run_id=%s status=%s new=%s updated=%s deleted=%s",
        report.run_id,
        report.status,
        report.reviews_new,
        report.reviews_updated,
        report.reviews_deleted,
    )
    return report.to_dict()


async def main() -> None:
    settings = load_settings()
    setup_logging(settings)

    parser = argparse.ArgumentParser(description="BrandMonitor crawl scheduler CLI")
    parser.add_argument("--db", default=os.getenv("DB_PATH", settings.db_path))
    parser.add_argument("--config", default=os.getenv("COMPANIES_CONFIG", "config/companies.yaml"))
    sub = parser.add_subparsers(dest="command", required=True)

    manual = sub.add_parser("manual", help="Run one crawl immediately")
    manual.add_argument("--company", required=True)
    manual.add_argument("--mode", default=settings.crawl_default_mode)
    manual.add_argument("--source", default="google_maps")
    manual.add_argument("--branch-place-id", default=None)
    manual.add_argument("--branch-name", default=None)
    manual.add_argument("--max-branches", type=int, default=None)
    manual.add_argument("--max-reviews-per-branch", type=int, default=None)
    manual.add_argument("--headed", action="store_true")

    all_cmd = sub.add_parser("all-companies", help="Crawl all enabled companies from config")
    all_cmd.add_argument("--mode", default=None)
    all_cmd.add_argument("--max-branches", type=int, default=None)
    all_cmd.add_argument("--max-reviews-per-branch", type=int, default=None)
    all_cmd.add_argument("--headed", action="store_true")

    sched = sub.add_parser("schedule", help="Run scheduled jobs for N ticks")
    sched.add_argument("--company", action="append", default=None)
    sched.add_argument("--from-config", action="store_true")
    sched.add_argument("--mode", default=settings.crawl_default_mode)
    sched.add_argument("--interval-seconds", type=int, default=3600)
    sched.add_argument("--ticks", type=int, default=1)
    sched.add_argument("--headed", action="store_true")

    retry = sub.add_parser("retry-failed", help="Re-queue failed tasks and resume run")
    retry.add_argument("--run-id", type=int, required=True)
    retry.add_argument("--headed", action="store_true")

    args = parser.parse_args()
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    db = Database(args.db)
    await db.connect()
    scheduler = CrawlScheduler()

    try:
        if args.command == "manual":
            spec = ScheduleSpec(company_name=args.company, mode=args.mode)
            result = await scheduler.run_manual(
                lambda s: _run_crawl(
                    db,
                    s,
                    headed=args.headed,
                    max_branches=args.max_branches,
                    max_reviews=args.max_reviews_per_branch,
                    branch_place_id=args.branch_place_id,
                    branch_name=args.branch_name,
                    source_id=args.source,
                ),
                spec,
            )
            print(json.dumps({"result": result, "metrics": METRICS.snapshot()}, indent=2, ensure_ascii=False))
        elif args.command == "all-companies":
            companies, defaults = load_company_config(args.config)
            mode = args.mode or defaults.mode
            results = []
            for company in companies:
                if not company.enabled:
                    continue
                spec = ScheduleSpec(company_name=company.query, mode=mode)
                result = await _run_crawl(
                    db,
                    spec,
                    headed=args.headed,
                    max_branches=args.max_branches,
                    max_reviews=args.max_reviews_per_branch,
                    source_id=company.source,
                )
                results.append({"company": company.name, "query": company.query, "result": result})
            print(json.dumps({"results": results, "metrics": METRICS.snapshot()}, indent=2, ensure_ascii=False))
        elif args.command == "schedule":
            if args.from_config or not args.company:
                for company in list_enabled_companies(args.config):
                    scheduler.add_job(
                        ScheduleSpec(
                            company_name=company.query,
                            mode=args.mode,
                            interval_seconds=company.schedule_interval_seconds,
                        )
                    )
            else:
                for company in args.company:
                    scheduler.add_job(
                        ScheduleSpec(
                            company_name=company,
                            mode=args.mode,
                            interval_seconds=args.interval_seconds,
                        )
                    )

            async def runner(spec: ScheduleSpec):
                return await _run_crawl(db, spec, headed=args.headed)

            await scheduler.run_forever(
                runner,
                tick_seconds=settings.scheduler_tick_seconds,
                max_ticks=args.ticks,
            )
            print(json.dumps({"metrics": METRICS.snapshot()}, indent=2))
        elif args.command == "retry-failed":
            async def resume(run_id: int):
                run = await db.get_crawl_run(run_id)
                if run is None:
                    raise SystemExit(f"Unknown run_id={run_id}")
                monitor = CrawlMonitor()
                source = build_source("google_maps", headless=not args.headed)
                crawler = ProductionCrawler(db, source, monitor=monitor)
                config = CrawlConfig(
                    company_name=run["company_name"],
                    mode=run.get("mode") or "incremental",
                    max_attempts=settings.crawl_max_attempts,
                    headless=not args.headed,
                )
                report = await crawler.run(config, run_id=run_id)
                return report.to_dict()

            out = await scheduler.retry_failed(db=db, run_id=args.run_id, runner=resume)
            print(json.dumps(out, indent=2, default=str, ensure_ascii=False))
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
