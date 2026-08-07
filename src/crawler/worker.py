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
    discover_week_ids,
    week_url,
)
from src.crawler.manager import CrawlerManager
from src.crawler.models import CrawlJob
from src.database.raw import RawRace
from src.datasources import get_datasource
from src.utils.settings import Settings, get_settings
from src.versioning.hashing import compute_source_hash


class CrawlWorker:
    """
    Processes crawl_jobs:
      - race_list → enqueue week jobs
      - week → expand rounds → enqueue race jobs
      - race → collect + persist Raw (skip unchanged via source_hash)
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
        week_ids = discover_week_ids(html)
        urls = [week_url(wid) for wid in week_ids]
        stats = self.manager.enqueue_many(job_type="week", urls=urls)
        logger.info("race_list discovery enqueued weeks={}", stats)
        return {"discovered_weeks": len(week_ids), **stats}

    def _handle_week(self, job: CrawlJob) -> dict[str, Any]:
        html = self._ensure_browser().fetch_html(job.url)
        race_urls = discover_race_urls_from_week_html(html, job.url)
        stats = self.manager.enqueue_many(job_type="race", urls=race_urls)
        logger.info("week expand enqueued races={}", stats)
        return {"discovered_races": len(race_urls), **stats}

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
        paths = collector.collect(job.url)
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
            # also try without query normalization mismatches — match by payload sourceUrl
            return None
        return row.source_hash

    def run_once(self, *, job_type: str | None = None) -> dict[str, Any] | None:
        job = self.manager.claim_next(job_type=job_type, worker_id=self.worker_id)
        if job is None:
            return None
        try:
            result = self.handle(job)
            if result.get("unchanged"):
                self.manager.mark_skipped_unchanged(job, result)
            else:
                self.manager.mark_success(job, result)
            self.session.commit()
            return {"job_id": job.id, "status": job.status, **result}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Worker {} job {} failed: {}", self.worker_id, job.id, exc)
            self.session.rollback()
            # re-load job in fresh state
            job = self.session.get(CrawlJob, job.id)
            if job is not None:
                self.manager.mark_failed(job, str(exc))
                self.session.commit()
            return {"job_id": job.id if job else None, "status": "failed", "error": str(exc)}
