"""Crawler manager — queue, resume, retry, duplicate prevention, progress."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.crawler.models import CrawlJob


def make_dedupe_key(job_type: str, url: str) -> str:
    parsed = urlparse(url)
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    if parsed.query:
        normalized = f"{normalized}?{parsed.query}"
    return f"{job_type}:{normalized}"


class CrawlerManager:
    """Production-oriented crawl queue (does not scrape itself)."""

    def __init__(self, session: Session, *, max_attempts: int = 3) -> None:
        self.session = session
        self.max_attempts = max_attempts

    def enqueue(
        self,
        *,
        job_type: str,
        url: str,
        payload: dict[str, Any] | None = None,
        max_attempts: int | None = None,
    ) -> CrawlJob:
        key = make_dedupe_key(job_type, url)
        existing = self.session.scalar(
            select(CrawlJob).where(
                CrawlJob.job_type == job_type,
                CrawlJob.dedupe_key == key,
            )
        )
        if existing is not None:
            if existing.status in {"success", "pending", "running", "skipped_duplicate"}:
                logger.info(
                    "Duplicate crawl prevented type={} url={} status={}",
                    job_type,
                    url,
                    existing.status,
                )
                return existing
            # failed → allow retry by resetting to pending
            existing.status = "pending"
            existing.last_error = None
            existing.payload_json = payload or existing.payload_json
            existing.updated_at = datetime.now(timezone.utc)
            self.session.flush()
            return existing

        job = CrawlJob(
            job_type=job_type,
            url=url,
            dedupe_key=key,
            status="pending",
            max_attempts=max_attempts or self.max_attempts,
            payload_json=payload,
        )
        self.session.add(job)
        self.session.flush()
        logger.info("Enqueued crawl job id={} type={} url={}", job.id, job_type, url)
        return job

    def claim_next(self, *, job_type: str | None = None) -> CrawlJob | None:
        stmt = select(CrawlJob).where(CrawlJob.status == "pending").order_by(CrawlJob.id)
        if job_type:
            stmt = stmt.where(CrawlJob.job_type == job_type)
        job = self.session.scalars(stmt).first()
        if job is None:
            return None
        job.status = "running"
        job.attempts += 1
        job.started_at = datetime.now(timezone.utc)
        job.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return job

    def mark_success(self, job: CrawlJob, result: dict[str, Any] | None = None) -> None:
        job.status = "success"
        job.result_json = result
        job.finished_at = datetime.now(timezone.utc)
        job.updated_at = datetime.now(timezone.utc)
        self.session.flush()

    def mark_failed(self, job: CrawlJob, error: str) -> None:
        job.last_error = error[:4000]
        job.updated_at = datetime.now(timezone.utc)
        if job.attempts >= job.max_attempts:
            job.status = "failed"
            job.finished_at = datetime.now(timezone.utc)
        else:
            job.status = "pending"  # retry later
        self.session.flush()

    def resume_failed(self) -> int:
        """Re-queue failed jobs that still have attempts remaining OR reset failed."""
        count = 0
        for job in self.session.scalars(select(CrawlJob).where(CrawlJob.status == "failed")):
            job.status = "pending"
            job.attempts = 0
            job.last_error = None
            job.updated_at = datetime.now(timezone.utc)
            count += 1
        self.session.flush()
        logger.info("Resumed {} failed crawl jobs", count)
        return count

    def progress(self) -> dict[str, int]:
        rows = self.session.execute(
            select(CrawlJob.status, func.count()).group_by(CrawlJob.status)
        ).all()
        return {status: int(count) for status, count in rows}

    def process_queue(
        self,
        handler: Callable[[CrawlJob], dict[str, Any] | None],
        *,
        limit: int = 10,
        job_type: str | None = None,
    ) -> dict[str, int]:
        """Claim and process up to `limit` jobs using the provided handler."""
        stats = {"success": 0, "failed": 0}
        for _ in range(limit):
            job = self.claim_next(job_type=job_type)
            if job is None:
                break
            try:
                result = handler(job)
                self.mark_success(job, result)
                stats["success"] += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception("Crawl job {} failed: {}", job.id, exc)
                self.mark_failed(job, str(exc))
                stats["failed"] += 1
        return stats
