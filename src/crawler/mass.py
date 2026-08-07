"""Mass crawl orchestration — multi-worker safe production runner."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from src.asbdavani.constants import RACECARDS_PATH, absolute_url
from src.crawler.manager import CrawlerManager
from src.crawler.stats import CrawlRun
from src.crawler.worker import CrawlWorker
from src.database.session import get_engine, session_scope
from src.utils.settings import Settings, get_settings
from sqlalchemy.orm import Session


def seed_discovery(session: Session, *, settings: Settings | None = None) -> dict[str, Any]:
    """Enqueue root race_list discovery job (idempotent)."""
    cfg = settings or get_settings()
    mgr = CrawlerManager(session, max_attempts=cfg.crawl_max_attempts)
    url = cfg.crawl_seed_url or absolute_url(RACECARDS_PATH)
    job = mgr.enqueue(job_type="race_list", url=url)
    return {"seed_job_id": job.id, "status": job.status}


def refresh_successful_races(session: Session, *, settings: Settings | None = None) -> int:
    """Re-queue completed race jobs so workers can detect website updates."""
    cfg = settings or get_settings()
    mgr = CrawlerManager(session, max_attempts=cfg.crawl_max_attempts)
    from sqlalchemy import select

    from src.crawler.models import CrawlJob

    count = 0
    for job in session.scalars(
        select(CrawlJob).where(
            CrawlJob.job_type.in_(["race", "refresh_race"]),
            CrawlJob.status.in_(["success", "skipped_unchanged"]),
        )
    ):
        mgr.enqueue(job_type="race", url=job.url, force=True)
        count += 1
    logger.info("Refresh queued for {} race jobs", count)
    return count


def _worker_loop(
    worker_index: int,
    *,
    settings: Settings,
    stop_event: threading.Event,
    counters: dict[str, int],
    lock: threading.Lock,
    idle_sleep: float = 1.5,
) -> None:
    worker_id = f"worker-{worker_index}"
    logger.info("Starting {}", worker_id)
    while not stop_event.is_set():
        try:
            with session_scope(settings) as session:
                worker = CrawlWorker(
                    session,
                    settings=settings,
                    worker_id=worker_id,
                )
                try:
                    result = worker.run_once()
                finally:
                    worker.close()

            if result is None:
                time.sleep(idle_sleep)
                continue

            with lock:
                status = result.get("status")
                if status == "failed":
                    counters["failed"] += 1
                elif status == "skipped_unchanged":
                    counters["unchanged"] += 1
                elif status == "skipped_out_of_scope":
                    counters["out_of_scope"] += 1
                else:
                    counters["success"] += 1
                    # race_list / week also count as success jobs; race paths mark collection
                    if result.get("paths"):
                        counters["races_collected"] += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("{} crashed: {}", worker_id, exc)
            time.sleep(idle_sleep)
    logger.info("{} exited", worker_id)


def run_mass_crawl(
    *,
    settings: Settings | None = None,
    workers: int | None = None,
    seed: bool = True,
    max_runtime_seconds: float | None = None,
) -> dict[str, Any]:
    """Run multi-worker crawl until the queue is drained (or timeout)."""
    cfg = settings or get_settings()
    n_workers = max(1, workers or cfg.crawl_workers)
    get_engine(cfg)

    with session_scope(cfg) as session:
        run = CrawlRun(status="running", workers=n_workers)
        session.add(run)
        session.flush()
        run_id = run.id
        if seed:
            seed_discovery(session, settings=cfg)
        CrawlerManager(session).requeue_stale_running(
            older_than_seconds=cfg.crawl_stale_running_seconds
        )

    started = time.perf_counter()
    stop_event = threading.Event()
    counters = {
        "success": 0,
        "failed": 0,
        "unchanged": 0,
        "out_of_scope": 0,
        "races_collected": 0,
    }
    lock = threading.Lock()
    threads: list[threading.Thread] = []

    for i in range(n_workers):
        t = threading.Thread(
            target=_worker_loop,
            kwargs={
                "worker_index": i + 1,
                "settings": cfg,
                "stop_event": stop_event,
                "counters": counters,
                "lock": lock,
            },
            daemon=True,
            name=f"crawl-worker-{i + 1}",
        )
        threads.append(t)
        t.start()

    empty_ticks = 0
    try:
        while any(t.is_alive() for t in threads):
            if max_runtime_seconds and (time.perf_counter() - started) >= max_runtime_seconds:
                logger.warning("Max runtime reached — stopping workers")
                stop_event.set()
                break

            with session_scope(cfg) as session:
                progress = CrawlerManager(session).progress()
            pending = int(progress.get("pending", 0))
            running = int(progress.get("running", 0))
            if pending + running == 0:
                empty_ticks += 1
                if empty_ticks >= 3:
                    logger.info("Queue drained — stopping workers")
                    stop_event.set()
                    break
            else:
                empty_ticks = 0
            time.sleep(1.0)

        for t in threads:
            t.join(timeout=120)
    finally:
        stop_event.set()

    duration = time.perf_counter() - started
    with session_scope(cfg) as session:
        run = session.get(CrawlRun, run_id)
        if run is not None:
            run.status = "success"
            run.finished_at = datetime.now(timezone.utc)
            run.duration_seconds = duration
            run.jobs_success = counters["success"]
            run.jobs_failed = counters["failed"]
            run.jobs_unchanged = counters["unchanged"]
            run.races_collected = counters["races_collected"]
            run.stats_json = dict(counters)
        progress = CrawlerManager(session).progress()

    summary = {
        "run_id": run_id,
        "workers": n_workers,
        "duration_seconds": round(duration, 2),
        **counters,
        "queue": progress,
    }
    logger.info("Mass crawl finished {}", summary)
    return summary
