"""Dashboard metrics for the production crawler (no analytics features)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.crawler.manager import CrawlerManager
from src.crawler.models import CrawlJob
from src.crawler.stats import CrawlRun
from src.database.raw import RawHorse, RawRace
from src.warehouse.models import (
    WhHorse,
    WhJockey,
    WhOwner,
    WhRace,
    WhRaceVideo,
    WhTrainer,
)


def _count(session: Session, model) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def collect_dashboard_metrics(session: Session) -> dict[str, Any]:
    queue = CrawlerManager(session).progress()
    pending = int(queue.get("pending", 0))
    running = int(queue.get("running", 0))
    success = int(queue.get("success", 0)) + int(queue.get("skipped_unchanged", 0))
    failed = int(queue.get("failed", 0))
    total_jobs = sum(queue.values()) or 0
    done = success + failed + int(queue.get("skipped_duplicate", 0))

    # Crawl speed from latest finished run
    latest = session.scalar(
        select(CrawlRun).where(CrawlRun.finished_at.is_not(None)).order_by(CrawlRun.id.desc())
    )
    crawl_speed = 0.0
    if latest and latest.duration_seconds and latest.duration_seconds > 0:
        crawl_speed = round(
            (latest.jobs_success + latest.jobs_unchanged) / latest.duration_seconds,
            3,
        )

    success_rate = round((success / done) * 100, 2) if done else 0.0
    remaining = pending + running
    eta_seconds = None
    if crawl_speed > 0 and remaining > 0:
        eta_seconds = round(remaining / crawl_speed, 1)

    # Prefer warehouse counts; fall back to raw
    races = _count(session, WhRace) or _count(session, RawRace)
    horses = _count(session, WhHorse) or _count(session, RawHorse)

    return {
        "total_races": races,
        "total_horses": horses,
        "total_jockeys": _count(session, WhJockey),
        "total_trainers": _count(session, WhTrainer),
        "total_owners": _count(session, WhOwner),
        "total_race_videos": _count(session, WhRaceVideo),
        "crawl_speed_jobs_per_sec": crawl_speed,
        "failed_pages": failed,
        "success_rate_percent": success_rate,
        "estimated_remaining_jobs": remaining,
        "estimated_remaining_seconds": eta_seconds,
        "queue": queue,
        "total_jobs": total_jobs,
        "raw_race_versions": _count(session, RawRace),
        "pending_jobs": pending,
        "running_jobs": running,
    }


def format_dashboard(metrics: dict[str, Any]) -> str:
    eta = metrics.get("estimated_remaining_seconds")
    eta_txt = f"{eta}s" if eta is not None else "n/a"
    lines = [
        "=== Crawler Dashboard ===",
        f"Total races:              {metrics.get('total_races', 0)}",
        f"Total horses:             {metrics.get('total_horses', 0)}",
        f"Total jockeys:            {metrics.get('total_jockeys', 0)}",
        f"Total trainers:           {metrics.get('total_trainers', 0)}",
        f"Total owners:             {metrics.get('total_owners', 0)}",
        f"Total race videos:        {metrics.get('total_race_videos', 0)}",
        f"Crawl speed:              {metrics.get('crawl_speed_jobs_per_sec', 0)} jobs/s",
        f"Failed pages:             {metrics.get('failed_pages', 0)}",
        f"Success rate:             {metrics.get('success_rate_percent', 0)}%",
        f"Estimated remaining work: {metrics.get('estimated_remaining_jobs', 0)} jobs (~{eta_txt})",
        f"Queue:                    {metrics.get('queue', {})}",
    ]
    return "\n".join(lines)
