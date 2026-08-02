from __future__ import annotations

import asyncio
import time
from pathlib import Path

from collectors.crawl_models import CrawlConfig
from collectors.google_maps.production_crawler import ProductionCrawler
from collectors.monitoring import CrawlMonitor
from core.db import Database
from models.branch import Branch
from models.review import Review


class StressSource:
    """Simulates many branches/reviews without network I/O."""

    def __init__(self, branches: int = 20, reviews_per_branch: int = 250):
        self.branches = [
            Branch(
                name=f"Branch {i}",
                address=f"City {i % 10}",
                place_id=f"place-{i}",
                company_name="StressCo",
            )
            for i in range(branches)
        ]
        self.reviews_per_branch = reviews_per_branch

    async def discover_branches(self, company_name: str) -> list[Branch]:
        return list(self.branches)

    async def collect_reviews(self, branch: Branch) -> list[Review]:
        idx = int(branch.place_id.split("-")[1])
        return [
            Review(
                author=f"user-{idx}-{j}",
                text=f"review text {idx}-{j} about delivery and service",
                rating=float((j % 5) + 1),
                external_id=f"ext-{idx}-{j}",
                branch_name=branch.name,
                published_at=f"day-{j}",
            )
            for j in range(self.reviews_per_branch)
        ]

    async def close(self) -> None:
        return None


def test_stress_thousands_of_reviews_and_report(tmp_path: Path):
    async def run() -> None:
        # 20 * 250 = 5000 reviews
        db_path = str(tmp_path / "stress.db")
        db = Database(db_path)
        await db.connect()
        source = StressSource(branches=20, reviews_per_branch=250)
        monitor = CrawlMonitor()
        crawler = ProductionCrawler(db, source, monitor=monitor)

        t0 = time.perf_counter()
        report = await crawler.run(
            CrawlConfig(company_name="StressCo", mode="full", max_attempts=1)
        )
        elapsed = time.perf_counter() - t0

        stats = await db.stats()
        assert stats["reviews"] == 5000
        assert report.reviews_new == 5000
        assert report.branches_succeeded == 20
        assert elapsed < 120  # generous for CI/cloud CPU

        # Incremental rerun: no new inserts; identical content is unchanged (not edited).
        source2 = StressSource(branches=20, reviews_per_branch=250)
        crawler2 = ProductionCrawler(db, source2, monitor=CrawlMonitor())
        report2 = await crawler2.run(
            CrawlConfig(company_name="StressCo", mode="incremental", max_attempts=1)
        )
        assert report2.reviews_new == 0
        assert report2.reviews_found == 5000
        assert report2.reviews_updated == 0

        saved = await db.get_crawl_report(report2.run_id)
        assert saved is not None
        assert saved["reviews_found"] == 5000
        print(
            {
                "elapsed_sec": round(elapsed, 3),
                "reviews": stats["reviews"],
                "report": saved,
                "monitor": monitor.summary(),
            }
        )
        await db.close()

    asyncio.run(run())
