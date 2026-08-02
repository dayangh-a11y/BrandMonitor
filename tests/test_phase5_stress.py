from __future__ import annotations

import asyncio
import time
from pathlib import Path

from collectors.crawl_models import CrawlConfig
from collectors.google_maps.production_crawler import ProductionCrawler
from collectors.monitoring import CrawlMonitor
from core.db import Database
from core.metrics import METRICS
from models.branch import Branch
from models.review import Review


class StressSource:
    def __init__(self, branches: int, reviews_per_branch: int, company: str = "StressCo"):
        self.company = company
        self.branches = [
            Branch(
                name=f"Branch {i}",
                address=f"City {i % 50}",
                place_id=f"place-{i}",
                company_name=company,
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
                text=f"review text {idx}-{j} about delivery and service quality",
                rating=float((j % 5) + 1),
                external_id=f"ext-{idx}-{j}",
                branch_name=branch.name,
                published_at=f"day-{j}",
            )
            for j in range(self.reviews_per_branch)
        ]

    async def close(self) -> None:
        return None


def test_stress_50000_fake_reviews(tmp_path: Path):
    """Bulk ingest 50,000 reviews and measure throughput."""

    async def run() -> dict:
        METRICS.reset()
        db = Database(str(tmp_path / "stress50k.db"))
        await db.connect()
        company_id = await db.upsert_company("BulkCo")
        branch_id = await db.upsert_branch(
            company_id,
            Branch(name="Bulk Branch", address="Tehran", company_name="BulkCo", place_id="bulk-1"),
        )

        batch_size = 2500
        total = 50_000
        t0 = time.perf_counter()
        written = 0
        for start in range(0, total, batch_size):
            reviews = [
                Review(
                    author=f"u-{i}",
                    text=f"bulk review {i}",
                    rating=float((i % 5) + 1),
                    external_id=f"bulk-ext-{i}",
                    published_at=f"t-{i}",
                )
                for i in range(start, min(start + batch_size, total))
            ]
            written += await db.upsert_reviews_batch(branch_id, reviews)
        elapsed = time.perf_counter() - t0
        stats = await db.stats()
        speed = written / elapsed if elapsed else 0.0
        METRICS.record_crawl(
            reviews_found=written,
            reviews_new=written,
            reviews_updated=0,
            duration_seconds=elapsed,
            branches=1,
        )
        # Duplicate import simulation on same batch subset
        dup = await db.upsert_reviews_batch(
            branch_id,
            [
                Review(
                    author="u-0",
                    text="bulk review 0",
                    rating=1.0,
                    external_id="bulk-ext-0",
                    published_at="t-0",
                )
            ]
            * 1,
        )
        assert dup == 1
        assert stats["reviews"] == 50_000
        assert written == 50_000
        assert elapsed < 180
        await db.close()
        return {
            "reviews": written,
            "elapsed_sec": round(elapsed, 3),
            "reviews_per_sec": round(speed, 1),
            "metrics": METRICS.snapshot(),
        }

    result = asyncio.run(run())
    print("STRESS_50K", result)
    assert result["reviews"] == 50_000


def test_stress_1000_branches(tmp_path: Path):
    """Crawl orchestration across 1,000 branches (2 reviews each)."""

    async def run() -> dict:
        METRICS.reset()
        db = Database(str(tmp_path / "stress1k.db"))
        await db.connect()
        source = StressSource(branches=1000, reviews_per_branch=2, company="ThousandCo")
        crawler = ProductionCrawler(db, source, monitor=CrawlMonitor())
        t0 = time.perf_counter()
        report = await crawler.run(
            CrawlConfig(company_name="ThousandCo", mode="full", max_attempts=1)
        )
        elapsed = time.perf_counter() - t0
        stats = await db.stats()
        METRICS.record_crawl(
            reviews_found=report.reviews_found,
            reviews_new=report.reviews_new,
            reviews_updated=report.reviews_updated,
            duration_seconds=elapsed,
            failed_branches=report.branches_failed,
            branches=report.branches_succeeded,
        )
        assert stats["branches"] == 1000
        assert stats["reviews"] == 2000
        assert report.branches_succeeded == 1000
        assert elapsed < 300
        health = await db.get_system_health()
        dash = await db.get_ops_dashboard()
        await db.close()
        return {
            "branches": stats["branches"],
            "reviews": stats["reviews"],
            "elapsed_sec": round(elapsed, 3),
            "avg_reviews_per_branch": dash["average_reviews_per_branch"],
            "health_status": health["status"],
            "metrics": METRICS.snapshot(),
        }

    result = asyncio.run(run())
    print("STRESS_1K_BRANCHES", result)
    assert result["branches"] == 1000
