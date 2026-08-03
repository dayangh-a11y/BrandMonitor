from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Protocol

from collectors.crawl_models import CrawlConfig, CrawlProgress, CrawlReport
from collectors.dedupe import branch_identity_key, review_fingerprint
from collectors.incremental import diff_reviews
from collectors.monitoring import CrawlMonitor
from core.db import Database
from core.logging_setup import get_logger
from core.metrics import METRICS
from models.branch import Branch
from models.review import Review

log = get_logger("crawler")


class BranchReviewSource(Protocol):
    async def discover_branches(self, company_name: str) -> list[Branch]:
        ...

    async def collect_reviews(self, branch: Branch) -> list[Review]:
        ...

    async def close(self) -> None:
        ...


class ProductionCrawler:
    """
    Production orchestration around a branch/review source.

    Supports resume, retries, soft-delete detection, incremental upserts,
    checkpoints, stats, and crawl reports.
    """

    def __init__(
        self,
        db: Database,
        source: BranchReviewSource,
        *,
        monitor: CrawlMonitor | None = None,
    ):
        self.db = db
        self.source = source
        self.monitor = monitor or CrawlMonitor()

    async def start_or_resume(self, config: CrawlConfig) -> int:
        existing = await self.db.find_resumable_crawl_run(config.company_name)
        if existing:
            run_id = int(existing["id"])
            await self.db.update_crawl_run_status(run_id, "running", started=True)
            self.monitor.event("resume_run", run_id=run_id, company=config.company_name)
            return run_id

        run_id = await self.db.create_crawl_run(
            company_name=config.company_name,
            mode=config.mode,
            config={
                "max_branches": config.max_branches,
                "max_reviews_per_branch": config.max_reviews_per_branch,
                "max_attempts": config.max_attempts,
                "headless": config.headless,
            },
        )
        await self.db.update_crawl_run_status(run_id, "running", started=True)
        self.monitor.event("start_run", run_id=run_id, company=config.company_name)
        return run_id

    async def run(self, config: CrawlConfig, *, run_id: int | None = None) -> CrawlReport:
        started = time.perf_counter()
        run_id = run_id or await self.start_or_resume(config)
        company_id = await self.db.upsert_company(config.company_name, source="google_maps")

        try:
            tasks = await self.db.list_crawl_branch_tasks(run_id)
            if not tasks:
                await self._discover_and_enqueue(run_id, company_id, config)
            else:
                # Resume path: still refresh discovery markers for deletion detection once.
                checkpoint = await self.db.get_checkpoint(run_id)
                if not checkpoint.get("discovery_completed"):
                    await self._discover_and_enqueue(run_id, company_id, config)

            if config.discovery_only:
                # Mark discovery tasks complete without touching review extraction.
                tasks_after = await self.db.list_crawl_branch_tasks(run_id)
                for task in tasks_after:
                    if task.get("status") in {"pending", "running"}:
                        await self.db.finish_branch_task(
                            int(task["id"]),
                            status="succeeded",
                            branch_id=task.get("branch_id"),
                        )
                await self.db.save_checkpoint(
                    run_id,
                    {
                        "discovery_completed": True,
                        "discovery_only": True,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                log.info(
                    "discovery_only_complete run_id=%s tasks=%s",
                    run_id,
                    len(tasks_after),
                )
            else:
                while True:
                    task = await self.db.claim_next_branch_task(run_id)
                    if task is None:
                        break
                    await self._crawl_one_branch(run_id, company_id, task, config)
                    await self.db.save_checkpoint(
                        run_id,
                        {
                            "discovery_completed": True,
                            "last_task_id": task["id"],
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        },
                    )

            progress_tasks = await self.db.list_crawl_branch_tasks(run_id)
            failed = sum(1 for t in progress_tasks if t.get("status") == "failed")
            succeeded = sum(1 for t in progress_tasks if t.get("status") == "succeeded")
            final_status = "succeeded"
            if failed > 0 and succeeded == 0:
                final_status = "failed"
            await self.db.update_crawl_run_status(run_id, final_status, finished=True)
            report = await self.build_report(run_id)
            report.duration_seconds = round(time.perf_counter() - started, 3)
            await self.db.save_crawl_report(run_id, report.to_dict())
            METRICS.record_crawl(
                reviews_found=report.reviews_found,
                reviews_new=report.reviews_new,
                reviews_updated=report.reviews_updated,
                duration_seconds=report.duration_seconds or 0.0,
                failed_branches=report.branches_failed,
                branches=report.branches_succeeded + report.branches_failed,
            )
            log.info(
                "crawl_finished run_id=%s status=%s reviews_new=%s duration=%s",
                run_id,
                final_status,
                report.reviews_new,
                report.duration_seconds,
            )
            self.monitor.event("finish_run", run_id=run_id, status=final_status)
            return report
        except Exception as exc:  # noqa: BLE001
            await self.db.update_crawl_run_status(
                run_id,
                "interrupted",
                error=str(exc),
                finished=True,
            )
            log.error("crawl_interrupted run_id=%s error=%s", run_id, exc)
            self.monitor.event("interrupt_run", run_id=run_id, error=str(exc))
            raise
        finally:
            await self.source.close()

    async def _discover_and_enqueue(
        self,
        run_id: int,
        company_id: int,
        config: CrawlConfig,
    ) -> None:
        discovered = await self.source.discover_branches(config.company_name)
        if config.max_branches is not None:
            discovered = discovered[: config.max_branches]

        existing_rows = await self.db.list_company_branch_rows(company_id)
        existing_by_key = {
            branch_identity_key(
                place_id=row.get("place_id") or "",
                name=row.get("name") or "",
                address=row.get("address") or "",
            ): row
            for row in existing_rows
        }
        seen_keys: set[str] = set()

        # Avoid duplicating tasks on resume.
        current_tasks = await self.db.list_crawl_branch_tasks(run_id)
        tasked_keys = {
            branch_identity_key(
                place_id=t.get("place_id") or "",
                name=t.get("branch_name") or "",
                address=t.get("address") or "",
            )
            for t in current_tasks
        }

        for branch in discovered:
            key = branch_identity_key(
                place_id=branch.place_id,
                name=branch.name,
                address=branch.address,
            )
            if config.branch_place_id and branch.place_id != config.branch_place_id:
                continue
            if config.branch_name and branch.name.casefold() != config.branch_name.casefold():
                continue
            seen_keys.add(key)
            branch_id = None
            if key in existing_by_key:
                branch_id = int(existing_by_key[key]["id"])
                # Refresh metadata for known branches.
                branch_id = await self.db.upsert_branch(company_id, branch)
            else:
                branch_id = await self.db.upsert_branch(company_id, branch)
            if key not in tasked_keys:
                await self.db.add_crawl_branch_task(
                    run_id,
                    branch_name=branch.name,
                    address=branch.address,
                    place_id=branch.place_id,
                    branch_id=branch_id,
                    max_attempts=config.max_attempts,
                )

        deleted_ids = []
        if (
            config.detect_deleted_branches
            and not config.branch_place_id
            and not config.branch_name
        ):
            deleted_ids = [
                int(row["id"])
                for key, row in existing_by_key.items()
                if key not in seen_keys and not int(row.get("is_deleted") or 0)
            ]
            if deleted_ids:
                await self.db.mark_branches_deleted(deleted_ids)
                for branch_id in deleted_ids:
                    row = next(r for r in existing_rows if int(r["id"]) == branch_id)
                    task_id = await self.db.add_crawl_branch_task(
                        run_id,
                        branch_name=row.get("name") or "",
                        address=row.get("address") or "",
                        place_id=row.get("place_id") or "",
                        branch_id=branch_id,
                        max_attempts=1,
                    )
                    await self.db.finish_branch_task(task_id, status="deleted", branch_id=branch_id)

        await self.db.record_crawl_stat(run_id, "branches_discovered", float(len(discovered)))
        await self.db.record_crawl_stat(run_id, "branches_deleted", float(len(deleted_ids)))
        await self.db.save_checkpoint(run_id, {"discovery_completed": True})
        self.monitor.event(
            "discovery_done",
            run_id=run_id,
            discovered=len(discovered),
            deleted=len(deleted_ids),
        )

    async def _crawl_one_branch(
        self,
        run_id: int,
        company_id: int,
        task: dict,
        config: CrawlConfig,
    ) -> None:
        if task.get("status") == "deleted":
            return
        branch = Branch(
            name=task.get("branch_name") or "",
            address=task.get("address") or "",
            place_id=task.get("place_id") or "",
            company_name=config.company_name,
            maps_url="",
        )
        if task.get("branch_id") is not None:
            row = await self.db.get_branch(int(task["branch_id"]))
            if row:
                branch = Branch(
                    name=row.get("name") or branch.name,
                    address=row.get("address") or branch.address,
                    place_id=row.get("place_id") or branch.place_id,
                    company_name=config.company_name,
                    maps_url=row.get("maps_url") or "",
                    phone=row.get("phone") or "",
                    latitude=row.get("latitude"),
                    longitude=row.get("longitude"),
                    city=row.get("city") or "",
                    province=row.get("province") or "",
                    rating=float(row.get("rating") or 0),
                    review_count=int(row.get("review_count") or 0),
                )
        elif branch.place_id and not branch.maps_url:
            branch.maps_url = f"https://www.google.com/maps/place/?q=place_id:{branch.place_id}"
        try:
            reviews = await self.source.collect_reviews(branch)
            if config.max_reviews_per_branch is not None:
                reviews = reviews[: config.max_reviews_per_branch]

            # Persist enriched metadata gathered while opening the place page.
            branch.review_count = max(int(branch.review_count or 0), len(reviews))
            branch_id = await self.db.upsert_branch(company_id, branch)
            await self.db.mark_branch_seen(branch_id)

            known_external, known_fp, known_hashes, active_rows = (
                await self.db.get_branch_known_review_keys(branch_id)
            )
            diff = diff_reviews(
                reviews,
                known_external_ids=known_external,
                known_fingerprints=known_fp,
                known_content_hashes=known_hashes,
                active_rows=active_rows if config.detect_deleted_reviews else [],
                fingerprint_fn=review_fingerprint,
                branch_key=str(branch_id),
            )

            upsert_batch = diff.new_reviews + diff.edited_reviews + diff.unchanged_reviews
            if upsert_batch:
                await self.db.upsert_reviews_batch(branch_id, upsert_batch)

            deleted_count = 0
            if config.detect_deleted_reviews and diff.deleted_review_ids:
                deleted_count = await self.db.mark_reviews_deleted(
                    branch_id, diff.deleted_review_ids
                )

            duplicates_skipped = len(diff.unchanged_reviews)
            await self.db.mark_branch_success(branch_id)
            await self.db.finish_branch_task(
                int(task["id"]),
                status="succeeded",
                branch_id=branch_id,
                reviews_found=len(reviews),
                reviews_new=len(diff.new_reviews),
                reviews_updated=len(diff.edited_reviews),
            )
            await self.db.record_crawl_stat(run_id, "reviews_found", float(len(reviews)))
            await self.db.record_crawl_stat(run_id, "reviews_new", float(len(diff.new_reviews)))
            await self.db.record_crawl_stat(
                run_id, "reviews_updated", float(len(diff.edited_reviews))
            )
            await self.db.record_crawl_stat(run_id, "reviews_deleted", float(deleted_count))
            await self.db.record_crawl_stat(
                run_id, "duplicates_skipped", float(duplicates_skipped)
            )
            self.monitor.event(
                "branch_succeeded",
                run_id=run_id,
                branch=branch.name,
                new=len(diff.new_reviews),
                updated=len(diff.edited_reviews),
                deleted=deleted_count,
                duplicates_skipped=duplicates_skipped,
            )
        except Exception as exc:  # noqa: BLE001
            status = "failed"
            await self.db.finish_branch_task(
                int(task["id"]),
                status=status,
                error=str(exc),
            )
            await self.db.record_crawl_stat(run_id, "branch_failures", 1.0)
            self.monitor.event(
                "branch_failed",
                run_id=run_id,
                branch=task.get("branch_name"),
                error=str(exc),
                attempt=task.get("attempts"),
            )

    async def get_progress(self, run_id: int) -> CrawlProgress:
        run = await self.db.get_crawl_run(run_id)
        tasks = await self.db.list_crawl_branch_tasks(run_id)
        stats = await self.db.get_crawl_stats(run_id)
        counts = {
            "pending": 0,
            "running": 0,
            "succeeded": 0,
            "failed": 0,
            "deleted": 0,
        }
        for task in tasks:
            status = task.get("status") or "pending"
            if status in counts:
                counts[status] += 1
        return CrawlProgress(
            run_id=run_id,
            status=(run or {}).get("status") or "queued",  # type: ignore[arg-type]
            total_branches=len(tasks),
            pending=counts["pending"],
            running=counts["running"],
            succeeded=counts["succeeded"],
            failed=counts["failed"],
            deleted=counts["deleted"],
            reviews_new=int(stats.get("reviews_new", 0)),
            reviews_updated=int(stats.get("reviews_updated", 0)),
        )

    async def build_report(self, run_id: int) -> CrawlReport:
        run = await self.db.get_crawl_run(run_id)
        assert run is not None
        tasks = await self.db.list_crawl_branch_tasks(run_id)
        stats = await self.db.get_crawl_stats(run_id)
        errors = [
            f"{t.get('branch_name')}: {t.get('last_error')}"
            for t in tasks
            if t.get("status") == "failed" and t.get("last_error")
        ]
        retries = sum(max(int(t.get("attempts") or 0) - 1, 0) for t in tasks)
        duration = None
        if run.get("started_at") and run.get("finished_at"):
            # best-effort; leave None if unparsable
            duration = None
        return CrawlReport(
            run_id=run_id,
            company_name=run["company_name"],
            mode=run["mode"],
            status=run["status"],
            started_at=run.get("started_at"),
            finished_at=run.get("finished_at"),
            duration_seconds=duration,
            branches_discovered=int(stats.get("branches_discovered", len(tasks))),
            branches_succeeded=sum(1 for t in tasks if t.get("status") == "succeeded"),
            branches_failed=sum(1 for t in tasks if t.get("status") == "failed"),
            branches_deleted=sum(1 for t in tasks if t.get("status") == "deleted"),
            reviews_found=int(stats.get("reviews_found", 0)),
            reviews_new=int(stats.get("reviews_new", 0)),
            reviews_updated=int(stats.get("reviews_updated", 0)),
            reviews_deleted=int(stats.get("reviews_deleted", 0)),
            retries=retries,
            errors=errors,
            stats=stats,
        )


class GoogleMapsBranchReviewSource:
    """Adapter over GoogleMapsCollector for production crawls."""

    def __init__(
        self,
        *,
        headless: bool = True,
        max_branches: int | None = None,
        max_reviews_per_branch: int | None = None,
        search_queries: list[str] | None = None,
    ):
        from collectors.google_maps.collector import GoogleMapsCollector

        self._collector = GoogleMapsCollector(
            headless=headless,
            max_branches=max_branches or 10_000,
            max_reviews_per_branch=max_reviews_per_branch or 10_000,
        )
        self._search_queries = list(search_queries or [])
        self._started = False

    async def _ensure_started(self) -> None:
        if not self._started:
            await self._collector.start()
            self._started = True

    async def discover_branches(self, company_name: str) -> list[Branch]:
        """Discover branches; optionally merge multiple Maps search queries."""
        await self._ensure_started()
        queries = self._search_queries or [company_name]
        merged: list[Branch] = []
        seen: set[str] = set()
        for query in queries:
            log.info("maps_discover_query query=%s", query)
            try:
                await self._collector.search(query)
                found = await self._collector.collect_branches(company_name=company_name)
            except Exception as exc:  # noqa: BLE001
                log.warning("maps_discover_query_failed query=%s error=%s", query, exc)
                continue
            for branch in found:
                key = branch_identity_key(
                    place_id=branch.place_id,
                    name=branch.name,
                    address=branch.address,
                )
                if key in seen:
                    continue
                seen.add(key)
                merged.append(branch)
        log.info(
            "maps_discover_merged company=%s queries=%s branches=%s",
            company_name,
            len(queries),
            len(merged),
        )
        return merged

    async def collect_reviews(self, branch: Branch) -> list[Review]:
        await self._ensure_started()
        return await self._collector.collect_reviews_for_branch(branch)

    async def close(self) -> None:
        if self._started:
            await self._collector.stop()
            self._started = False
