"""Crawl job handlers — discovery expansion + race collection (no ML)."""

from __future__ import annotations

import time
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.asbdavani.constants import RACECARDS_PATH, absolute_url
from src.browser import BrowserClient
from src.collectors import RaceCollector
from src.crawler.discovery import (
    discover_race_urls_from_week_html,
    discover_weeks,
    location_from_week_html,
    normalize_job_url,
    week_url,
)
from src.crawler.manager import CrawlerManager
from src.crawler.models import CrawlJob
from src.database.raw import RawRace
from src.datasources import get_datasource
from src.racecourses import (
    OutOfScopeRacecourseError,
    allowed_codes_from_settings,
    ensure_track_in_scope,
)
from src.utils.settings import Settings, get_settings
from src.utils.retry import ParseError


class CrawlWorker:
    """
    Processes crawl_jobs:
      - race_list → enqueue week jobs (racecourse-scoped)
      - week → expand rounds → enqueue race jobs (skip out-of-scope)
      - race → collect + persist Raw (skip unchanged / out-of-scope)
    """

    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        worker_id: str = "worker-1",
        datasource_name: str | None = None,
        collect_histories: bool | None = None,
        crawl_delay_seconds: float | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.worker_id = worker_id
        self.datasource_name = datasource_name or self.settings.default_datasource
        self.collect_histories = (
            self.settings.crawl_collect_histories
            if collect_histories is None
            else collect_histories
        )
        self.crawl_delay = (
            self.settings.crawl_delay_seconds
            if crawl_delay_seconds is None
            else crawl_delay_seconds
        )
        self.manager = CrawlerManager(
            session, max_attempts=self.settings.crawl_max_attempts
        )
        self._browser: BrowserClient | None = None
        self._datasource = None

    def _allowed_codes(self) -> frozenset[str] | None:
        return allowed_codes_from_settings(self.settings)

    def _ensure_browser(self) -> BrowserClient:
        if self._browser is None:
            self._browser = BrowserClient(self.settings)
            self._browser.start()
        return self._browser

    def _ensure_datasource(self):
        if self._datasource is None:
            # Reuse shared browser for discovery fetches
            from src.asbdavani.source import AsbdavaniDataSource

            if self.datasource_name == "asbdavani":
                self._datasource = AsbdavaniDataSource(
                    browser=self._ensure_browser(),
                    settings=self.settings,
                    owns_browser=False,
                )
            else:
                self._datasource = get_datasource(self.datasource_name)
        return self._datasource

    def close(self) -> None:
        if self._datasource is not None:
            # only close if it owns resources; asbdavani with owns_browser=False is fine
            try:
                self._datasource.close()
            except Exception:  # noqa: BLE001
                pass
            self._datasource = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None

    def _delay(self) -> None:
        if self.crawl_delay > 0:
            time.sleep(self.crawl_delay)

    def handle(self, job: CrawlJob) -> dict[str, Any]:
        self._delay()
        if job.job_type in {"race_list", "discover"}:
            return self._handle_race_list(job)
        if job.job_type == "week":
            return self._handle_week(job)
        if job.job_type in {"race", "refresh_race"}:
            return self._handle_race(job)
        raise ValueError(f"Unsupported job_type={job.job_type}")

    def _handle_race_list(self, job: CrawlJob) -> dict[str, Any]:
        url = job.url or absolute_url(RACECARDS_PATH)
        html = self._ensure_browser().fetch_html(url)
        weeks = discover_weeks(html, allowed_codes=self._allowed_codes())
        urls = [week_url(w.week_id) for w in weeks]
        stats = self.manager.enqueue_many(
            job_type="week",
            urls=urls,
        )
        # Attach location onto newly pending week jobs when known
        for week in weeks:
            if not week.location:
                continue
            key_url = normalize_job_url(week_url(week.week_id))
            existing = self.session.scalar(
                select(CrawlJob).where(
                    CrawlJob.job_type == "week",
                    CrawlJob.url == key_url,
                )
            )
            if existing is not None:
                payload = dict(existing.payload_json or {})
                payload["location"] = week.location
                if week.racecourse_code:
                    payload["racecourse_code"] = week.racecourse_code
                existing.payload_json = payload
        self.session.flush()
        logger.info(
            "race_list discovery enqueued weeks={} (scope={})",
            stats,
            self.settings.crawl_allowed_racecourses,
        )
        return {
            "discovered_weeks": len(weeks),
            "allowed_racecourses": self.settings.crawl_allowed_racecourses,
            **stats,
        }

    def _handle_week(self, job: CrawlJob) -> dict[str, Any]:
        html = self._ensure_browser().fetch_html(job.url)
        location = location_from_week_html(html)
        if location is None and isinstance(job.payload_json, dict):
            location = job.payload_json.get("location")
        try:
            course = ensure_track_in_scope(location, settings=self.settings)
        except OutOfScopeRacecourseError as exc:
            logger.info(
                "Skipping week out of scope url={} track={!r}",
                job.url,
                location,
            )
            return {
                "out_of_scope": True,
                "track": location,
                "racecourse_code": exc.racecourse_code,
                "discovered_races": 0,
                "enqueued": 0,
                "skipped": 0,
                "total_urls": 0,
            }

        race_urls = discover_race_urls_from_week_html(html, job.url)
        stats = self.manager.enqueue_many(job_type="race", urls=race_urls)
        code = course.code if course else None
        logger.info(
            "week expand enqueued races={} track={!r} code={}",
            stats,
            location,
            code,
        )
        return {
            "discovered_races": len(race_urls),
            "track": location,
            "racecourse_code": code,
            **stats,
        }

    def _handle_race(self, job: CrawlJob) -> dict[str, Any]:
        datasource = self._ensure_datasource()
        collector = RaceCollector(
            datasource=datasource,
            settings=self.settings,
            output_dir=self.settings.output_dir / "crawl" / self.worker_id,
            collect_histories=self.collect_histories,
            persist_to_db=True,
        )
        before_hash = self._current_raw_hash_for_url(job.url)
        try:
            paths = collector.collect(job.url)
        except OutOfScopeRacecourseError as exc:
            logger.info(
                "Skipping race out of scope url={} track={!r}",
                job.url,
                exc.track,
            )
            return {
                "out_of_scope": True,
                "url": job.url,
                "track": exc.track,
                "racecourse_code": exc.racecourse_code,
            }
        except ParseError as exc:
            # Unknown / missing racecourse → treat as out of scope when scoped crawl
            msg = str(exc)
            if "racecourse" in msg.lower() or "track" in msg.lower():
                logger.info("Skipping race (racecourse parse): {} ({})", job.url, msg)
                return {
                    "out_of_scope": True,
                    "url": job.url,
                    "error": msg,
                }
            raise
        self.session.expire_all()
        after_hash = self._current_raw_hash_for_url(job.url)
        unchanged = (
            before_hash is not None
            and after_hash is not None
            and before_hash == after_hash
        )
        return {
            "url": job.url,
            "paths": {k: str(v) for k, v in paths.items()},
            "unchanged": unchanged,
            "source_hash": after_hash,
        }

    def _current_raw_hash_for_url(self, url: str) -> str | None:
        row = self.session.scalar(
            select(RawRace).where(
                RawRace.source_url == url,
                RawRace.is_current.is_(True),
            )
        )
        if row is None:
            return None
        return row.source_hash

    def run_once(self, *, job_type: str | None = None) -> dict[str, Any] | None:
        job = self.manager.claim_next(job_type=job_type, worker_id=self.worker_id)
        if job is None:
            return None
        job_id = job.id
        # Release the claim write-lock before Raw ingest opens a second session
        # (required for SQLite; safe for Postgres multi-worker too).
        self.session.commit()
        try:
            result = self.handle(job)
            # Refresh after possible concurrent Raw writes on another connection.
            self.session.refresh(job)
            if result.get("out_of_scope"):
                self.manager.mark_skipped_out_of_scope(job, result)
            elif result.get("unchanged"):
                self.manager.mark_skipped_unchanged(job, result)
            else:
                self.manager.mark_success(job, result)
            self.session.commit()
            return {"job_id": job.id, "status": job.status, **result}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Worker {} job {} failed: {}", self.worker_id, job_id, exc)
            self.session.rollback()
            job = self.session.get(CrawlJob, job_id)
            if job is not None:
                self.manager.mark_failed(job, str(exc))
                self.session.commit()
            return {"job_id": job_id, "status": "failed", "error": str(exc)}
