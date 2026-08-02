#!/usr/bin/env python3
"""
Private-beta ops cycle: crawl enabled companies → MVP pipeline (AI → insights → scores).

Does not change score_v1 or public API response shapes. Intended for host cron.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from collectors.company_config import load_company_config
from collectors.crawl_models import CrawlConfig
from collectors.google_maps.production_crawler import ProductionCrawler
from collectors.monitoring import CrawlMonitor
from collectors.sources.registry import build_source
from core.config import load_settings
from core.db import Database
from core.logging_setup import get_logger, setup_logging
from core.metrics import METRICS, flush_metrics_to_db

log = get_logger("scheduler")


async def _crawl_company(
    db: Database,
    *,
    query: str,
    source_id: str,
    mode: str,
    headed: bool,
    max_branches: int | None,
    max_reviews: int | None,
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
        company_name=query,
        mode=mode,  # type: ignore[arg-type]
        max_attempts=settings.crawl_max_attempts,
        headless=not headed and settings.headless,
        max_branches=max_branches,
        max_reviews_per_branch=max_reviews,
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
    return report.to_dict()


def _run_mvp_pipeline_subprocess(*, db_path: str, limit: int, provider: str | None) -> dict:
    cmd = [
        sys.executable,
        "scripts/run_mvp_pipeline.py",
        "--db",
        db_path,
        "--limit",
        str(limit),
    ]
    if provider:
        cmd.extend(["--provider", provider])
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", ".")
    proc = subprocess.run(
        cmd,
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"MVP pipeline failed (exit={proc.returncode}): {proc.stderr or proc.stdout}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"raw_stdout": proc.stdout[-2000:], "stderr": proc.stderr[-1000:]}


async def main() -> None:
    settings = load_settings()
    setup_logging(settings)
    parser = argparse.ArgumentParser(description="Crawl → MVP pipeline beta cycle")
    parser.add_argument("--db", default=os.getenv("DB_PATH", settings.db_path))
    parser.add_argument("--config", default=os.getenv("COMPANIES_CONFIG", "config/companies.yaml"))
    parser.add_argument("--company", default=None, help="Optional single company name from config")
    parser.add_argument("--mode", default=None)
    parser.add_argument("--max-branches", type=int, default=None)
    parser.add_argument("--max-reviews-per-branch", type=int, default=None)
    parser.add_argument("--pipeline-limit", type=int, default=500)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--skip-crawl", action="store_true")
    parser.add_argument("--skip-pipeline", action="store_true")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    db = Database(args.db)
    await db.connect()

    crawl_results: list[dict] = []
    pipeline_result: dict | None = None
    try:
        if not args.skip_crawl:
            companies, defaults = load_company_config(args.config)
            mode = args.mode or defaults.mode
            for company in companies:
                if not company.enabled:
                    continue
                if args.company and company.name != args.company and company.query != args.company:
                    continue
                result = await _crawl_company(
                    db,
                    query=company.query,
                    source_id=company.source,
                    mode=mode,
                    headed=args.headed,
                    max_branches=args.max_branches,
                    max_reviews=args.max_reviews_per_branch,
                )
                crawl_results.append(
                    {"company": company.name, "query": company.query, "result": result}
                )
                log.info(
                    "beta_crawl_done company=%s status=%s",
                    company.name,
                    result.get("status"),
                )

        if not args.skip_pipeline:
            pipeline_result = _run_mvp_pipeline_subprocess(
                db_path=args.db,
                limit=args.pipeline_limit,
                provider=args.provider,
            )
            log.info("beta_pipeline_done")

        flushed = await flush_metrics_to_db(db)
        summary = {
            "crawl_results": crawl_results,
            "pipeline": pipeline_result,
            "metrics_flushed": flushed,
            "metrics": METRICS.snapshot(),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
