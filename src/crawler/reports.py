"""Daily crawl report generation."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.crawler.metrics import collect_dashboard_metrics, format_dashboard
from src.crawler.models import CrawlJob
from src.crawler.stats import CrawlDailyReport, CrawlRun
from src.utils.settings import Settings, get_settings


def _jobs_finished_on(session: Session, day: date) -> dict[str, int]:
    # Compare by date portion of finished_at / updated_at
    rows = session.scalars(
        select(CrawlJob).where(CrawlJob.finished_at.is_not(None))
    ).all()
    counts = {"success": 0, "failed": 0, "skipped_unchanged": 0, "other": 0}
    for job in rows:
        finished = job.finished_at
        if finished is None:
            continue
        if finished.astimezone(timezone.utc).date() != day:
            continue
        if job.status in counts:
            counts[job.status] += 1
        else:
            counts["other"] += 1
    return counts


def generate_daily_report(
    session: Session,
    *,
    report_date: date | None = None,
    settings: Settings | None = None,
) -> tuple[CrawlDailyReport, str]:
    cfg = settings or get_settings()
    day = report_date or datetime.now(timezone.utc).date()
    metrics = collect_dashboard_metrics(session)
    day_jobs = _jobs_finished_on(session, day)

    runs_today = session.scalars(
        select(CrawlRun).where(CrawlRun.finished_at.is_not(None))
    ).all()
    runs_count = sum(
        1
        for r in runs_today
        if r.finished_at and r.finished_at.astimezone(timezone.utc).date() == day
    )

    payload: dict[str, Any] = {
        "report_date": day.isoformat(),
        "dashboard": metrics,
        "jobs_finished_today": day_jobs,
        "crawl_runs_finished_today": runs_count,
    }

    text = "\n".join(
        [
            f"=== Daily Crawl Report ({day.isoformat()}) ===",
            format_dashboard(metrics),
            "",
            "--- Today ---",
            f"Crawl runs finished: {runs_count}",
            f"Jobs success:        {day_jobs.get('success', 0)}",
            f"Jobs unchanged:      {day_jobs.get('skipped_unchanged', 0)}",
            f"Jobs failed:         {day_jobs.get('failed', 0)}",
        ]
    )

    existing = session.scalar(
        select(CrawlDailyReport).where(CrawlDailyReport.report_date == day)
    )
    if existing is None:
        existing = CrawlDailyReport(report_date=day, metrics_json=payload, report_text=text)
        session.add(existing)
    else:
        existing.metrics_json = payload
        existing.report_text = text
    session.flush()

    out_dir = Path(cfg.log_dir) / "daily_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"crawl_report_{day.isoformat()}.txt"
    path.write_text(text + "\n", encoding="utf-8")
    logger.info("Wrote daily crawl report {}", path)
    return existing, text
