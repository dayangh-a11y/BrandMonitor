"""Crawler manager — queue, resume, retry, duplicate prevention, progress."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from loguru import logger
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from src.crawler.models import CrawlJob
from src.crawler.discovery import normalize_job_url


def make_dedupe_key(job_type: str, url: str) -> str:
    return f"{job_type}:{normalize_job_url(url)}"


class CrawlerManager:
    """Production-oriented crawl queue with multi-worker-safe claiming."""

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
        force: bool = False,
    ) -> CrawlJob:
        """
        Enqueue a job. Skips if already success/pending/running unless force=True
        (used for refresh / update detection).
        """
        url = normalize_job_url(url)
        key = make_dedupe_key(job_type, url)
        existing = self.session.scalar(
            select(CrawlJob).where(
                CrawlJob.job_type == job_type,
                CrawlJob.dedupe_key == key,
            )
        )
        if existing is not None:
            if force:
                existing.status = "pending"
                existing.attempts = 0
                existing.last_error = None
                existing.worker_id = None
                existing.finished_at = None
                existing.payload_json = payload or existing.payload_json
                existing.updated_at = datetime.now(timezone.utc)
                self.session.flush()
                logger.info("Force re-queued job id={} type={}", existing.id, job_type)
                return existing
            if existing.status in {
                "success",
                "pending",
                "running",
                "skipped_duplicate",
                "skipped_unchanged",
            }:
                logger.debug(
                    "Skip enqueue duplicate type={} url={} status={}",
                    job_type,
                    url,
                    existing.status,
                )
                return existing
            # failed → retry
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

    def enqueue_many(
        self,
        *,
        job_type: str,
        urls: list[str],
        force: bool = False,
    ) -> dict[str, int]:
        created = skipped = 0
        for url in urls:
            before = self.session.scalar(
                select(CrawlJob.status).where(
                    CrawlJob.job_type == job_type,
                    CrawlJob.dedupe_key == make_dedupe_key(job_type, url),
                )
            )
            job = self.enqueue(job_type=job_type, url=url, force=force)
            if before is None:
                created += 1
            elif force or before == "failed":
                created += 1
            else:
                skipped += 1
            _ = job
        return {"enqueued": created, "skipped": skipped, "total_urls": len(urls)}

    def claim_next(
        self,
        *,
        job_type: str | None = None,
        worker_id: str | None = None,
    ) -> CrawlJob | None:
        """
        Atomically claim one pending job.

        PostgreSQL: SKIP LOCKED. SQLite/others: optimistic UPDATE WHERE pending.
        """
        bind = self.session.get_bind()
        dialect = bind.dialect.name if bind is not None else ""

        if dialect == "postgresql":
            return self._claim_postgres(job_type=job_type, worker_id=worker_id)
        return self._claim_optimistic(job_type=job_type, worker_id=worker_id)

    def _claim_postgres(
        self, *, job_type: str | None, worker_id: str | None
    ) -> CrawlJob | None:
        params: dict[str, Any] = {}
        type_clause = ""
        if job_type:
            type_clause = "AND job_type = :job_type"
            params["job_type"] = job_type
        # SELECT ... FOR UPDATE SKIP LOCKED then update
        sql = text(
            f"""
            SELECT id FROM crawl_jobs
            WHERE status = 'pending' {type_clause}
            ORDER BY id
            FOR UPDATE SKIP LOCKED
            LIMIT 1
            """
        )
        row = self.session.execute(sql, params).first()
        if row is None:
            return None
        job_id = int(row[0])
        job = self.session.get(CrawlJob, job_id)
        if job is None:
            return None
        job.status = "running"
        job.attempts += 1
        job.worker_id = worker_id
        job.started_at = datetime.now(timezone.utc)
        job.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return job

    def _claim_optimistic(
        self, *, job_type: str | None, worker_id: str | None
    ) -> CrawlJob | None:
        stmt = select(CrawlJob).where(CrawlJob.status == "pending").order_by(CrawlJob.id)
        if job_type:
            stmt = stmt.where(CrawlJob.job_type == job_type)
        candidate = self.session.scalars(stmt).first()
        if candidate is None:
            return None
        job_id = candidate.id
        next_attempts = int(candidate.attempts) + 1
        now = datetime.now(timezone.utc)
        result = self.session.execute(
            update(CrawlJob)
            .where(CrawlJob.id == job_id, CrawlJob.status == "pending")
            .values(
                status="running",
                attempts=next_attempts,
                worker_id=worker_id,
                started_at=now,
                updated_at=now,
            )
        )
        if int(result.rowcount or 0) != 1:
            return None
        self.session.flush()
        return self.session.get(CrawlJob, job_id)

    def mark_success(self, job: CrawlJob, result: dict[str, Any] | None = None) -> None:
        job.status = "success"
        job.result_json = result
        job.finished_at = datetime.now(timezone.utc)
        job.updated_at = datetime.now(timezone.utc)
        job.last_error = None
        self.session.flush()

    def mark_skipped_unchanged(
        self, job: CrawlJob, result: dict[str, Any] | None = None
    ) -> None:
        job.status = "skipped_unchanged"
        job.result_json = result
        job.finished_at = datetime.now(timezone.utc)
        job.updated_at = datetime.now(timezone.utc)
        self.session.flush()

    def mark_failed(self, job: CrawlJob, error: str) -> None:
        job.last_error = error[:4000]
        job.updated_at = datetime.now(timezone.utc)
        logger.error(
            "Crawl job failed id={} type={} attempt={}/{} error={}",
            job.id,
            job.job_type,
            job.attempts,
            job.max_attempts,
            error,
        )
        if job.attempts >= job.max_attempts:
            job.status = "failed"
            job.finished_at = datetime.now(timezone.utc)
        else:
            job.status = "pending"
            job.worker_id = None
        self.session.flush()

    def resume_failed(self) -> int:
        count = 0
        for job in self.session.scalars(select(CrawlJob).where(CrawlJob.status == "failed")):
            job.status = "pending"
            job.attempts = 0
            job.last_error = None
            job.worker_id = None
            job.updated_at = datetime.now(timezone.utc)
            count += 1
        self.session.flush()
        logger.info("Resumed {} failed crawl jobs", count)
        return count

    def requeue_stale_running(self, *, older_than_seconds: int = 3600) -> int:
        """Recover jobs stuck in running after worker crash."""
        cutoff = datetime.now(timezone.utc).timestamp() - older_than_seconds
        count = 0
        for job in self.session.scalars(select(CrawlJob).where(CrawlJob.status == "running")):
            started = job.started_at or job.updated_at
            if started is None:
                continue
            if started.timestamp() > cutoff:
                continue
            job.status = "pending"
            job.worker_id = None
            job.updated_at = datetime.now(timezone.utc)
            count += 1
        self.session.flush()
        if count:
            logger.warning("Re-queued {} stale running jobs", count)
        return count

    def progress(self) -> dict[str, int]:
        rows = self.session.execute(
            select(CrawlJob.status, func.count()).group_by(CrawlJob.status)
        ).all()
        return {status: int(count) for status, count in rows}

    def pending_count(self, job_type: str | None = None) -> int:
        stmt = select(func.count()).select_from(CrawlJob).where(CrawlJob.status == "pending")
        if job_type:
            stmt = stmt.where(CrawlJob.job_type == job_type)
        return int(self.session.scalar(stmt) or 0)

    def process_queue(
        self,
        handler: Callable[[CrawlJob], dict[str, Any] | None],
        *,
        limit: int = 10,
        job_type: str | None = None,
    ) -> dict[str, int]:
        stats = {"success": 0, "failed": 0, "skipped_unchanged": 0}
        for _ in range(limit):
            job = self.claim_next(job_type=job_type)
            if job is None:
                break
            try:
                result = handler(job) or {}
                if result.get("unchanged"):
                    self.mark_skipped_unchanged(job, result)
                    stats["skipped_unchanged"] += 1
                else:
                    self.mark_success(job, result)
                    stats["success"] += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception("Crawl job {} failed: {}", job.id, exc)
                self.mark_failed(job, str(exc))
                stats["failed"] += 1
        return stats
