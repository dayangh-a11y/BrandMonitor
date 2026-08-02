from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Protocol

from collectors.crawl_models import CrawlConfig, CrawlProgress, CrawlReport
from collectors.dedupe import branch_identity_key, review_fingerprint
from collectors.incremental import filter_incremental_reviews
from collectors.monitoring import CrawlMonitor
from core.db import Database
from models.branch import Branch
from models.review import Review


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
            self.monitor.event("finish_run", run_id=run_id, status=final_status)
            return report
        except Exception as exc:  # noqa: BLE001
            await self.db.update_crawl_run_status(
                run_id,
                "interrupted",
                error=str(exc),
                finished=True,
            )
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
            seen_keys.add(key)
            branch_id = None
            if key in existing_by_key:
                branch_id = int(existing_by_key[key]["id"])
            if key not in tasked_keys:
                await self.db.add_crawl_branch_task(
                    run_id,
                    branch_name=branch.name,
                    address=branch.address,
                    place_id=branch.place_id,
                    branch_id=branch_id,
                    max_attempts=config.max_attempts,
                )

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
        try:
            reviews = await self.source.collect_reviews(branch)
            if config.max_reviews_per_branch is not None:
                reviews = reviews[: config.max_reviews_per_branch]

            branch_id = task.get("branch_id")
            if branch_id is None:
                # Persist discovered branch metadata with review_count estimate.
                branch.review_count = len(reviews)
                branch_id = await self.db.upsert_branch(company_id, branch)
            else:
                branch_id = int(branch_id)
                await self.db.mark_branch_seen(branch_id)

            known_external, known_fp = await self.db.get_branch_known_review_keys(branch_id)
            if config.mode == "incremental":
                new_reviews, existing_reviews = filter_incremental_reviews(
                    reviews,
                    known_external_ids=known_external,
                    known_fingerprints=known_fp,
                    fingerprint_fn=review_fingerprint,
                    branch_key=str(branch_id),
                )
            else:
                # Full mode still upserts; treat unknown as new and known as updates.
                new_reviews, existing_reviews = filter_incremental_reviews(
                    reviews,
                    known_external_ids=known_external,
                    known_fingerprints=known_fp,
                    fingerprint_fn=review_fingerprint,
                    branch_key=str(branch_id),
                )

            for review in new_reviews + existing_reviews:
                await self.db.upsert_review(branch_id, review)

            await self.db.finish_branch_task(
                int(task["id"]),
                status="succeeded",
                branch_id=branch_id,
                reviews_found=len(reviews),
                reviews_new=len(new_reviews),
                reviews_updated=len(existing_reviews),
            )
            await self.db.record_crawl_stat(run_id, "reviews_found", float(len(reviews)))
            await self.db.record_crawl_stat(run_id, "reviews_new", float(len(new_reviews)))
            await self.db.record_crawl_stat(run_id, "reviews_updated", float(len(existing_reviews)))
            self.monitor.event(
                "branch_succeeded",
                run_id=run_id,
                branch=branch.name,
                new=len(new_reviews),
                updated=len(existing_reviews),
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
    ):
        from collectors.google_maps.collector import GoogleMapsCollector

        self._collector = GoogleMapsCollector(
            headless=headless,
            max_branches=max_branches or 10_000,
            max_reviews_per_branch=max_reviews_per_branch or 10_000,
        )
        self._started = False

    async def _ensure_started(self) -> None:
        if not self._started:
            await self._collector.start()
            self._started = True

    async def discover_branches(self, company_name: str) -> list[Branch]:
        await self._ensure_started()
        await self._collector.search(company_name)
        return await self._collector.collect_branches(company_name=company_name)

    async def collect_reviews(self, branch: Branch) -> list[Review]:
        await self._ensure_started()
        return await self._collector.collect_reviews_for_branch(branch)

    async def close(self) -> None:
        if self._started:
            await self._collector.stop()
            self._started = False
