from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from core.logging_setup import get_logger
from core.metrics import METRICS

log = get_logger("scheduler")


@dataclass
class ScheduleSpec:
    company_name: str
    mode: str = "incremental"
    interval_seconds: int = 3600


class CrawlScheduler:
    """
    In-process scheduler for production crawl jobs.

    Supports:
    - manual one-shot runs
    - fixed-interval scheduled runs
    - retry of failed branch tasks / interrupted runs
    """

    def __init__(self):
        self._jobs: list[ScheduleSpec] = []

    def add_job(self, spec: ScheduleSpec) -> None:
        self._jobs.append(spec)
        log.info(
            "schedule_job_added company=%s mode=%s interval=%s",
            spec.company_name,
            spec.mode,
            spec.interval_seconds,
        )

    @property
    def jobs(self) -> list[ScheduleSpec]:
        return list(self._jobs)

    async def run_manual(
        self,
        runner: Callable[[ScheduleSpec], Awaitable[object]],
        spec: ScheduleSpec,
    ) -> object:
        log.info("manual_run company=%s mode=%s", spec.company_name, spec.mode)
        with METRICS.time_block("scheduler_manual_run_ms", company=spec.company_name):
            return await runner(spec)

    async def run_once(
        self,
        runner: Callable[[ScheduleSpec], Awaitable[object]],
    ) -> list[object]:
        results = []
        for job in self._jobs:
            results.append(await self.run_manual(runner, job))
        return results

    async def retry_failed(
        self,
        *,
        db,
        run_id: int,
        runner: Callable[[int], Awaitable[object]] | None = None,
    ) -> dict:
        """
        Re-queue failed branch tasks for a crawl run and optionally resume.

        Returns counts of tasks reset and runner result if provided.
        """
        reset = await db.reset_failed_branch_tasks(run_id)
        await db.update_crawl_run_status(run_id, "queued")
        log.info("retry_failed run_id=%s reset_tasks=%s", run_id, reset)
        METRICS.incr("scheduler_retries", reset)
        result = None
        if runner is not None:
            with METRICS.time_block("scheduler_retry_run_ms", run_id=str(run_id)):
                result = await runner(run_id)
        return {"run_id": run_id, "reset_tasks": reset, "result": result}

    async def run_forever(
        self,
        runner: Callable[[ScheduleSpec], Awaitable[object]],
        *,
        tick_seconds: int = 1,
        max_ticks: int | None = None,
    ) -> None:
        """
        Run due jobs forever (or until max_ticks for tests).

        Uses simple fixed-interval scheduling per job.
        """
        last_run: dict[str, float] = {}
        ticks = 0
        log.info("scheduler_started jobs=%s tick=%s", len(self._jobs), tick_seconds)
        while True:
            now = datetime.now(timezone.utc).timestamp()
            for job in self._jobs:
                key = f"{job.company_name}:{job.mode}"
                prev = last_run.get(key)
                if prev is None or (now - prev) >= job.interval_seconds:
                    try:
                        await self.run_manual(runner, job)
                        last_run[key] = now
                        METRICS.incr("scheduler_runs_succeeded")
                    except Exception as exc:  # noqa: BLE001
                        log.error(
                            "scheduled_run_failed company=%s error=%s",
                            job.company_name,
                            exc,
                            extra={"error": str(exc)},
                        )
                        METRICS.incr("scheduler_runs_failed")
                        last_run[key] = now
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                log.info("scheduler_stopped ticks=%s", ticks)
                return
            await asyncio.sleep(tick_seconds)
