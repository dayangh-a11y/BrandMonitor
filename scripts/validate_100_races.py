"""One-off production validation: crawl first 100 races and emit metrics.

Not part of platform architecture — validation harness only.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

# Use local SQLite for this environment
DB_PATH = Path("/workspace/output/validation/horse_racing.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["CRAWL_DELAY_SECONDS"] = "0.8"
os.environ["CRAWL_WORKERS"] = "3"
os.environ["CRAWL_COLLECT_HISTORIES"] = "false"
os.environ["LOG_LEVEL"] = "INFO"
os.environ["OUTPUT_DIR"] = "output/validation"
os.environ["LOG_DIR"] = "logs/validation"

from sqlalchemy import func, select

from src.asbdavani.constants import absolute_url
from src.browser import BrowserClient
from src.crawler.discovery import discover_race_urls_from_week_html, discover_week_ids, week_url
from src.crawler.manager import CrawlerManager
from src.crawler.metrics import collect_dashboard_metrics
from src.crawler.worker import CrawlWorker
from src.crawler.models import CrawlJob
from src.database import init_db, reset_engine, session_scope
from src.database.raw import RawHorse, RawParserError, RawRace, RawRaceEntry
from src.quality import format_quality_report, run_quality_checks
from src.quality.models import QualityIssue
from src.utils.logging import setup_logging
from src.utils.settings import get_settings
from src.warehouse import build_warehouse, run_entity_resolution
from src.warehouse.models import (
    WhEntityMatch,
    WhHorse,
    WhJockey,
    WhOwner,
    WhRace,
    WhRaceResult,
    WhTrainer,
)


TARGET_RACES = 100


def main() -> None:
    reset_engine()
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    init_db(settings)

    browser = BrowserClient(settings)
    browser.start()
    race_urls: list[str] = []
    try:
        print("Discovering weeks from racecards…")
        list_html = browser.fetch_html(settings.crawl_seed_url)
        week_ids = discover_week_ids(list_html)
        print(f"Found {len(week_ids)} weeks")

        for wid in week_ids:
            if len(race_urls) >= TARGET_RACES:
                break
            wurl = week_url(wid)
            print(f"Expanding week {wid} ({len(race_urls)}/{TARGET_RACES})…")
            try:
                whtml = browser.fetch_html(wurl)
                found = discover_race_urls_from_week_html(whtml, wurl)
            except Exception as exc:  # noqa: BLE001
                print(f"  week expand failed: {exc}")
                continue
            for u in found:
                if u not in race_urls:
                    race_urls.append(u)
                if len(race_urls) >= TARGET_RACES:
                    break
            time.sleep(settings.crawl_delay_seconds)
    finally:
        browser.close()

    race_urls = race_urls[:TARGET_RACES]
    print(f"Enqueueing {len(race_urls)} race jobs…")

    with session_scope(settings) as session:
        mgr = CrawlerManager(session, max_attempts=settings.crawl_max_attempts)
        for u in race_urls:
            mgr.enqueue(job_type="race", url=u)

    # Process queue with one worker (browser reused; claim commits release SQLite locks)
    started = time.perf_counter()
    success = failed = unchanged = 0
    timings: list[float] = []

    with session_scope(settings) as session:
        worker = CrawlWorker(session, settings=settings, worker_id="validation-1")
        try:
            while True:
                mgr = CrawlerManager(session)
                pending = mgr.pending_count(job_type="race")
                running = int(mgr.progress().get("running", 0))
                if pending + running == 0 and mgr.pending_count() == 0:
                    break
                t0 = time.perf_counter()
                result = worker.run_once(job_type="race")
                dt = time.perf_counter() - t0
                if result is None:
                    time.sleep(0.5)
                    continue
                timings.append(dt)
                status = result.get("status")
                print(
                    f"  job {result.get('job_id')} -> {status} ({dt:.1f}s) "
                    f"total_done={success + failed + unchanged + 1}"
                )
                if status == "failed":
                    failed += 1
                elif status == "skipped_unchanged":
                    unchanged += 1
                else:
                    success += 1
        finally:
            worker.close()

    elapsed = time.perf_counter() - started
    print(f"Crawl finished in {elapsed:.1f}s success={success} failed={failed} unchanged={unchanged}")

    print("Building warehouse + entity resolution + quality…")
    with session_scope(settings) as session:
        wh_stats = build_warehouse(session)
        entity_matches = run_entity_resolution(session)
        quality = run_quality_checks(session)
        metrics = collect_dashboard_metrics(session)

        sample_race = session.scalar(select(WhRace).order_by(WhRace.id).limit(1))
        sample_horse = session.scalar(select(WhHorse).order_by(WhHorse.id).limit(1))
        sample_result = None
        if sample_race is not None:
            sample_result = session.scalar(
                select(WhRaceResult).where(WhRaceResult.race_id == sample_race.id).limit(1)
            )

        raw_races = int(session.scalar(select(func.count()).select_from(RawRace)) or 0)
        raw_horses = int(session.scalar(select(func.count()).select_from(RawHorse)) or 0)
        parser_errors = int(session.scalar(select(func.count()).select_from(RawParserError)) or 0)
        dupes = int(
            session.scalar(
                select(func.count()).select_from(WhEntityMatch).where(
                    WhEntityMatch.status == "candidate"
                )
            )
            or 0
        )

        sample_race_payload = None
        if sample_race is not None:
            sample_race_payload = {
                "id": sample_race.id,
                "name": sample_race.name,
                "date": str(sample_race.race_date),
                "track": sample_race.track,
                "distance": sample_race.distance,
                "race_number": sample_race.race_number,
                "source_url": sample_race.source_url,
            }
        sample_horse_payload = None
        if sample_horse is not None:
            sample_horse_payload = {
                "id": sample_horse.id,
                "name": sample_horse.name,
                "sex": sample_horse.sex,
                "birthdate": str(sample_horse.birthdate) if sample_horse.birthdate else None,
                "profile_url": sample_horse.profile_url,
                "source_horse_id": sample_horse.source_horse_id,
            }

        avg_time = round(sum(timings) / len(timings), 2) if timings else 0.0
        done = success + failed + unchanged
        success_rate = round((success + unchanged) / done * 100, 2) if done else 0.0

        # Missing-field breakdown from latest quality issues
        missing_fields: dict[str, int] = {}
        for issue in session.scalars(
            select(QualityIssue).where(QualityIssue.check_name == "missing_values")
        ):
            field = (issue.details_json or {}).get("field") or issue.message
            missing_fields[str(field)] = missing_fields.get(str(field), 0) + 1

        broken_pages = [
            {"id": j.id, "url": j.url, "error": (j.last_error or "")[:500]}
            for j in session.scalars(
                select(CrawlJob).where(
                    CrawlJob.job_type == "race",
                    CrawlJob.status == "failed",
                )
            )
        ]

        parser_error_samples = [
            {
                "id": e.id,
                "error_type": e.error_type,
                "message": e.message,
                "source_url": e.source_url,
            }
            for e in session.scalars(select(RawParserError).limit(20))
        ]

        duplicate_samples = [
            {
                "entity_type": m.entity_type,
                "left_key": m.left_key,
                "right_key": m.right_key,
                "score": m.score,
                "method": m.method,
            }
            for m in session.scalars(
                select(WhEntityMatch)
                .where(WhEntityMatch.status == "candidate")
                .limit(20)
            )
        ]

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "target_races": TARGET_RACES,
            "enqueued_races": len(race_urls),
            "crawl": {
                "success": success,
                "failed": failed,
                "unchanged": unchanged,
                "elapsed_seconds": round(elapsed, 2),
                "avg_processing_time_seconds": avg_time,
                "success_rate_percent": success_rate,
            },
            "warehouse": wh_stats,
            "entity_matches": entity_matches,
            "quality": quality,
            "quality_text": format_quality_report(quality),
            "dashboard": metrics,
            "counts": {
                "total_races": metrics.get("total_races"),
                "total_horses": metrics.get("total_horses"),
                "total_jockeys": metrics.get("total_jockeys"),
                "total_trainers": metrics.get("total_trainers"),
                "total_owners": metrics.get("total_owners"),
                "raw_race_rows": raw_races,
                "raw_horse_rows": raw_horses,
                "parser_errors": parser_errors,
                "duplicate_entities": dupes,
            },
            "missing_fields": missing_fields,
            "broken_pages": broken_pages,
            "parser_error_samples": parser_error_samples,
            "duplicate_samples": duplicate_samples,
            "sample_race": sample_race_payload,
            "sample_horse": sample_horse_payload,
            "sample_result": (
                {
                    "finish_position": sample_result.finish_position,
                    "weight": sample_result.weight,
                    "time_raw": sample_result.time_raw,
                }
                if sample_result
                else None
            ),
        }

    out = Path("/workspace/output/validation/validation_data.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path = Path("/workspace/output/validation/VALIDATION_REPORT.md")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    print(f"Wrote {out}")
    print(f"Wrote {md_path}")
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2))


def _render_markdown(report: dict) -> str:
    c = report["counts"]
    crawl = report["crawl"]
    q = report["quality"]
    missing = report.get("missing_fields") or {}
    broken = report.get("broken_pages") or []
    sample_race = report.get("sample_race") or {}
    sample_horse = report.get("sample_horse") or {}

    missing_lines = (
        "\n".join(f"- `{k}`: {v}" for k, v in sorted(missing.items(), key=lambda x: -x[1]))
        if missing
        else "- None"
    )
    broken_lines = (
        "\n".join(
            f"- job `{b['id']}`: {b['url']}\n  - error: `{b['error']}`" for b in broken[:25]
        )
        if broken
        else "- None"
    )
    dup_lines = (
        "\n".join(
            f"- `{d['entity_type']}` score={d['score']} "
            f"`{d['left_key']}` ≈ `{d['right_key']}` ({d['method']})"
            for d in (report.get("duplicate_samples") or [])[:15]
        )
        if report.get("duplicate_samples")
        else "- None (no candidate matches)"
    )
    parse_lines = (
        "\n".join(
            f"- `{e.get('error_type')}`: {e.get('message')} ({e.get('source_url')})"
            for e in (report.get("parser_error_samples") or [])[:15]
        )
        if report.get("parser_error_samples")
        else "- None"
    )

    return f"""# Production Validation Report

Generated: `{report.get('generated_at')}`

Validation crawl of the first **{report.get('enqueued_races')}** race pages from asbdavani.app (target {report.get('target_races')}).

## Totals

| Entity | Count |
|--------|------:|
| Races | {c.get('total_races')} |
| Horses | {c.get('total_horses')} |
| Jockeys | {c.get('total_jockeys')} |
| Trainers | {c.get('total_trainers')} |
| Owners | {c.get('total_owners')} |
| Raw race rows | {c.get('raw_race_rows')} |
| Raw horse rows | {c.get('raw_horse_rows')} |

## Crawl performance

| Metric | Value |
|--------|------:|
| Success | {crawl.get('success')} |
| Failed (broken pages) | {crawl.get('failed')} |
| Skipped unchanged | {crawl.get('unchanged')} |
| Success rate | {crawl.get('success_rate_percent')}% |
| Average processing time | {crawl.get('avg_processing_time_seconds')}s |
| Total elapsed | {crawl.get('elapsed_seconds')}s |

## Missing fields

Total missing-value issues: **{q.get('missing_value_count', 0)}**

{missing_lines}

## Duplicate entities

Candidate duplicate matches: **{c.get('duplicate_entities')}**

{dup_lines}

## Parsing failures

Parser error rows: **{c.get('parser_errors')}**

{parse_lines}

## Broken pages

Failed race jobs: **{len(broken)}**

{broken_lines}

## Quality summary

```
{report.get('quality_text', '')}
```

## Sample race

```json
{json.dumps(sample_race, ensure_ascii=False, indent=2)}
```

## Sample horse

```json
{json.dumps(sample_horse, ensure_ascii=False, indent=2)}
```

## Sample result (from sample race)

```json
{json.dumps(report.get('sample_result'), ensure_ascii=False, indent=2)}
```
"""


if __name__ == "__main__":
    main()
