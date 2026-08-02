from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class ScheduleSpec:
    company_name: str
    mode: str = "incremental"
    interval_seconds: int = 3600


class CrawlScheduler:
    """Simple in-process scheduler for production crawl jobs."""

    def __init__(self):
        self._jobs: list[ScheduleSpec] = []

    def add_job(self, spec: ScheduleSpec) -> None:
        self._jobs.append(spec)

    @property
    def jobs(self) -> list[ScheduleSpec]:
        return list(self._jobs)

    async def run_once(
        self,
        runner: Callable[[ScheduleSpec], Awaitable[object]],
    ) -> list[object]:
        results = []
        for job in self._jobs:
            results.append(await runner(job))
        return results

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
        while True:
            now = datetime.now(timezone.utc).timestamp()
            for job in self._jobs:
                key = f"{job.company_name}:{job.mode}"
                prev = last_run.get(key)
                if prev is None or (now - prev) >= job.interval_seconds:
                    await runner(job)
                    last_run[key] = now
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                return
            await asyncio.sleep(tick_seconds)
