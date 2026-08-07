"""Operational historical collection for approved racecourses.

Not platform architecture — runs existing crawler/warehouse/quality APIs
and prints progress every 500 races.
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

os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ.setdefault("CRAWL_DELAY_SECONDS", "1.0")
os.environ.setdefault("CRAWL_WORKERS", "1")
os.environ.setdefault("CRAWL_COLLECT_HISTORIES", "false")
os.environ.setdefault(
    "CRAWL_ALLOWED_RACECOURSES",
    "gonbad-kavous,aq-qala,bandar-torkaman",
)
os.environ.setdefault("OUTPUT_DIR", "output/historical")
os.environ.setdefault("LOG_DIR", "logs/historical")
os.environ.setdefault("LOG_LEVEL", "INFO")

from sqlalchemy import func, select

from src.crawler.manager import CrawlerManager
from src.crawler.mass import seed_discovery
from src.crawler.models import CrawlJob
from src.crawler.worker import CrawlWorker
from src.database import init_db, reset_engine, session_scope
from src.database.raw import RawRace
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

MILESTONE = 500


def _count(session, model) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


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
    return {
        "at": datetime.now(timezone.utc).isoformat(),
        "races_collected": _count(session, WhRace) or _count(session, RawRace),
        "horses_collected": _count(session, WhHorse),
        "jockeys_collected": _count(session, WhJockey),
        "trainers_collected": _count(session, WhTrainer),
        "owners_collected": _count(session, WhOwner),
        "videos_collected": _count(session, WhRaceVideo),
        "failed_pages": failed,
        "duplicates": dupes,
        "raw_races": _count(session, RawRace),
        "queue": dict(queue),
    }


def print_progress(label: str, snap: dict) -> None:
    lines = [
        "",
        f"=== {label} ===",
        f"Time:                 {snap['at']}",
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
    text = "\n".join(lines)
    print(text, flush=True)
    path = PROGRESS_DIR / f"progress_{snap['races_collected']:05d}.md"
    path.write_text(
        f"# Collection progress — {snap['races_collected']} races\n\n"
        + "\n".join(
            f"- **{k.replace('_', ' ').title()}:** {v}"
            for k, v in snap.items()
            if k not in {"at", "queue"}
        )
        + f"\n\nQueue: `{snap['queue']}`\nGenerated: `{snap['at']}`\n",
        encoding="utf-8",
    )
    (PROGRESS_DIR / "latest.json").write_text(
        json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def refresh_warehouse_snapshot(settings) -> dict:
    with session_scope(settings) as session:
        build_warehouse(session)
        run_entity_resolution(session)
        run_quality_checks(session)
        return snapshot(session)


def main() -> None:
    reset_engine()
    settings = get_settings()
    setup_logging(settings.log_dir, settings.log_level)
    init_db(settings)

    print(
        f"Historical collection starting\n"
        f"  db={settings.database_url}\n"
        f"  scope={settings.crawl_allowed_racecourses}\n"
        f"  delay={settings.crawl_delay_seconds}s\n",
        flush=True,
    )

    with session_scope(settings) as session:
        seed_discovery(session, settings=settings)

    next_milestone = MILESTONE
    race_success = 0
    idle_rounds = 0
    started = time.perf_counter()

    # Keep one browser-backed worker across jobs for throughput.
    with session_scope(settings) as session:
        worker = CrawlWorker(session, settings=settings, worker_id="historical-1")
        try:
            while True:
                mgr = CrawlerManager(session)
                pending = mgr.pending_count()
                running = int(mgr.progress().get("running", 0))
                if pending + running == 0:
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
                if result.get("paths") and status in {"success", "skipped_unchanged"}:
                    race_success += 1
                    print(
                        f"  race ok #{race_success} job={result.get('job_id')} "
                        f"status={status} ({time.perf_counter() - started:.0f}s)",
                        flush=True,
                    )

                # Milestone based on Raw races (always current during crawl)
                with session_scope(settings) as s2:
                    raw_n = _count(s2, RawRace)
                if raw_n >= next_milestone:
                    snap = refresh_warehouse_snapshot(settings)
                    print_progress(f"PROGRESS @ {next_milestone} races", snap)
                    while raw_n >= next_milestone:
                        next_milestone += MILESTONE
        finally:
            worker.close()

    snap = refresh_warehouse_snapshot(settings)
    print_progress("FINAL", snap)
    elapsed = time.perf_counter() - started
    print(f"Collection finished in {elapsed:.1f}s", flush=True)
    (PROGRESS_DIR / "final.json").write_text(
        json.dumps({"elapsed_seconds": round(elapsed, 1), **snap}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
