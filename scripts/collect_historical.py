"""Nationwide historical collection — every official race week / city.

Removes the Golestan-only allowlist. Resumes safely, forces race_list
re-discovery so remaining weeks enqueue, and prints progress every 100
collected weeks.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB_PATH = Path("/workspace/output/historical/horse_racing.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
PROGRESS_DIR = Path("/workspace/output/historical/progress")
PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
ARTIFACTS_DIR = Path("/opt/cursor/artifacts")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ.setdefault("CRAWL_DELAY_SECONDS", "1.0")
os.environ.setdefault("CRAWL_WORKERS", "1")
os.environ.setdefault("CRAWL_COLLECT_HISTORIES", "false")
# Nationwide — every city / week on the index.
os.environ["CRAWL_ALLOWED_RACECOURSES"] = "*"
os.environ.setdefault("OUTPUT_DIR", "output/historical")
os.environ.setdefault("LOG_DIR", "logs/historical")
os.environ.setdefault("LOG_LEVEL", "INFO")

from sqlalchemy import func, select, text

from src.asbdavani.constants import RACECARDS_PATH, absolute_url
from src.crawler.manager import CrawlerManager
from src.crawler.mass import seed_discovery
from src.crawler.worker import CrawlWorker
from src.database import init_db, reset_engine, session_scope
from src.database.raw import RawRace, RawRaceEntry
from src.quality import run_quality_checks
from src.utils.logging import setup_logging
from src.utils.settings import get_settings
from src.warehouse import build_warehouse, run_entity_resolution
from src.warehouse.models import (
    WhEntityMatch,
    WhHorse,
    WhJockey,
    WhOwner,
    WhRace,
    WhRaceVideo,
    WhTrainer,
)

WEEK_MILESTONE = 100
EXPECTED_INDEX_WEEKS = 182  # asbdavani racecards index size at last audit


def _count(session, model) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def week_success_count(session) -> int:
    row = session.execute(
        text(
            "SELECT COUNT(*) FROM crawl_jobs "
            "WHERE job_type='week' AND status IN ('success','skipped_unchanged')"
        )
    ).scalar()
    return int(row or 0)


def snapshot(session) -> dict:
    queue = CrawlerManager(session).progress()
    failed = int(queue.get("failed", 0))
    dupes = int(
        session.scalar(
            select(func.count())
            .select_from(WhEntityMatch)
            .where(WhEntityMatch.status == "candidate")
        )
        or 0
    )
    races = _count(session, WhRace) or _count(session, RawRace)
    weeks = week_success_count(session)
    coverage = round(100.0 * weeks / EXPECTED_INDEX_WEEKS, 2) if EXPECTED_INDEX_WEEKS else None
    tracks = [
        {"track": t, "races": int(n)}
        for t, n in session.execute(
            text(
                "SELECT track, COUNT(*) AS n FROM wh_races "
                "GROUP BY track ORDER BY n DESC"
            )
        ).fetchall()
    ]
    return {
        "at": datetime.now(timezone.utc).isoformat(),
        "weeks_collected": weeks,
        "week_coverage_pct": coverage,
        "expected_index_weeks": EXPECTED_INDEX_WEEKS,
        "races_collected": races,
        "horses_collected": _count(session, WhHorse),
        "jockeys_collected": _count(session, WhJockey),
        "trainers_collected": _count(session, WhTrainer),
        "owners_collected": _count(session, WhOwner),
        "videos_collected": _count(session, WhRaceVideo),
        "failed_pages": failed,
        "duplicates": dupes,
        "raw_races": _count(session, RawRace),
        "raw_entries": _count(session, RawRaceEntry),
        "races_by_track": tracks,
        "queue": dict(queue),
        "scope": "nationwide",
    }


def print_progress(label: str, snap: dict) -> None:
    lines = [
        "",
        f"=== {label} ===",
        f"Time:                 {snap['at']}",
        f"Weeks collected:      {snap['weeks_collected']} / {snap['expected_index_weeks']} "
        f"({snap['week_coverage_pct']}%)",
        f"Races collected:      {snap['races_collected']}",
        f"Horses collected:     {snap['horses_collected']}",
        f"Jockeys collected:    {snap['jockeys_collected']}",
        f"Trainers collected:   {snap['trainers_collected']}",
        f"Owners collected:     {snap['owners_collected']}",
        f"Videos collected:     {snap['videos_collected']}",
        f"Failed pages:         {snap['failed_pages']}",
        f"Duplicates:           {snap['duplicates']}",
        f"Raw race rows:        {snap['raw_races']}",
        f"Queue:                {snap['queue']}",
        "",
    ]
    text_out = "\n".join(lines)
    print(text_out, flush=True)
    weeks = int(snap["weeks_collected"])
    path = PROGRESS_DIR / f"progress_weeks_{weeks:04d}.md"
    path.write_text(
        f"# Collection progress — {weeks} weeks\n\n"
        + "\n".join(
            f"- **{k.replace('_', ' ').title()}:** {v}"
            for k, v in snap.items()
            if k not in {"at", "queue", "races_by_track"}
        )
        + f"\n\nQueue: `{snap['queue']}`\nGenerated: `{snap['at']}`\n",
        encoding="utf-8",
    )
    (PROGRESS_DIR / "latest.json").write_text(
        json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    art = ARTIFACTS_DIR / f"nationwide_progress_weeks_{weeks:04d}.json"
    art.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")


def refresh_warehouse_snapshot(settings) -> dict:
    with session_scope(settings) as session:
        build_warehouse(session)
        run_entity_resolution(session)
        run_quality_checks(session)
        return snapshot(session)


def force_nationwide_rediscovery(settings) -> None:
    """Force race_list so newly allowed weeks are enqueued."""
    with session_scope(settings) as session:
        mgr = CrawlerManager(session, max_attempts=settings.crawl_max_attempts)
        url = settings.crawl_seed_url or absolute_url(RACECARDS_PATH)
        job = mgr.enqueue(job_type="race_list", url=url, force=True)
        print(
            f"Forced nationwide race_list rediscovery job_id={job.id} status={job.status}",
            flush=True,
        )


def main() -> None:
    reset_engine()
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    init_db(settings)

    print(
        f"Nationwide historical collection starting/resuming\n"
        f"  db={settings.database_url}\n"
        f"  scope={settings.crawl_allowed_racecourses}\n"
        f"  delay={settings.crawl_delay_seconds}s\n"
        f"  week_milestone={WEEK_MILESTONE}\n",
        flush=True,
    )

    with session_scope(settings) as session:
        prog = CrawlerManager(session).progress()
        total = sum(prog.values())
        if total == 0:
            seed_discovery(session, settings=settings)
        else:
            CrawlerManager(session).requeue_stale_running(older_than_seconds=0)
            print(f"Resuming existing queue: {prog}", flush=True)

    # Always re-run discovery under nationwide scope so the remaining
    # ~40% of weeks leave the historical Golestan allowlist.
    force_nationwide_rediscovery(settings)

    reported_milestones: set[int] = set()
    for p in PROGRESS_DIR.glob("progress_weeks_*.md"):
        try:
            reported_milestones.add(int(p.stem.split("_")[-1]))
        except (IndexError, ValueError):
            pass

    with session_scope(settings) as session:
        baseline = snapshot(session)
    print_progress("BASELINE", baseline)
    last_reported_bucket = baseline["weeks_collected"] // WEEK_MILESTONE

    from sqlalchemy.orm import sessionmaker

    from src.database.session import get_engine

    get_engine(settings)
    SessionLocal = sessionmaker(
        bind=get_engine(settings), autoflush=False, autocommit=False
    )

    session = SessionLocal()
    worker = CrawlWorker(session, settings=settings, worker_id="nationwide-1")
    started = time.perf_counter()
    race_success = 0
    idle_rounds = 0

    try:
        while True:
            prog = CrawlerManager(session).progress()
            pending = int(prog.get("pending", 0)) + int(prog.get("running", 0))
            if pending == 0:
                idle_rounds += 1
                if idle_rounds >= 3:
                    break
                time.sleep(1.0)
                continue
            idle_rounds = 0

            result = worker.run_once()
            if result is None:
                time.sleep(0.5)
                continue

            status = result.get("status")
            job_id = result.get("job_id")
            if result.get("paths") and status in {"success", "skipped_unchanged"}:
                race_success += 1
                print(
                    f"  race ok #{race_success} job={job_id} status={status} "
                    f"({time.perf_counter() - started:.0f}s)",
                    flush=True,
                )
            elif status in {"success", "skipped_unchanged", "skipped_out_of_scope"}:
                print(
                    f"  job ok job={job_id} status={status} "
                    f"discovered_weeks={result.get('discovered_weeks')} "
                    f"discovered_races={result.get('discovered_races')} "
                    f"track={result.get('track')!r}",
                    flush=True,
                )

            weeks_now = week_success_count(session)
            bucket = weeks_now // WEEK_MILESTONE
            if bucket > last_reported_bucket and weeks_now >= WEEK_MILESTONE:
                # Release crawler DB connection before warehouse write.
                worker.close()
                session.close()
                snap = refresh_warehouse_snapshot(settings)
                print_progress(
                    f"PROGRESS @ {snap['weeks_collected']} weeks "
                    f"({snap['week_coverage_pct']}% coverage)",
                    snap,
                )
                reported_milestones.add(int(snap["weeks_collected"]))
                last_reported_bucket = bucket
                session = SessionLocal()
                worker = CrawlWorker(
                    session, settings=settings, worker_id="nationwide-1"
                )
    finally:
        worker.close()
        session.close()

    snap = refresh_warehouse_snapshot(settings)
    print_progress("FINAL", snap)
    elapsed = time.perf_counter() - started
    print(f"Collection finished in {elapsed:.1f}s", flush=True)
    final_payload = {"elapsed_seconds": round(elapsed, 1), **snap}
    (PROGRESS_DIR / "final.json").write_text(
        json.dumps(final_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (ARTIFACTS_DIR / "nationwide_collection_final.json").write_text(
        json.dumps(final_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
