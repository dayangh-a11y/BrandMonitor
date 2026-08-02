from __future__ import annotations

import asyncio
from pathlib import Path

from collectors.crawl_models import CrawlConfig
from collectors.dedupe import is_duplicate_fingerprint, review_fingerprint
from collectors.google_maps.production_crawler import ProductionCrawler
from collectors.incremental import filter_incremental_reviews
from collectors.monitoring import CrawlMonitor
from collectors.scheduler import CrawlScheduler, ScheduleSpec
from core.db import Database
from models.branch import Branch
from models.review import Review


class FakeSource:
    def __init__(self):
        self.branches = [
            Branch(name="HQ", address="Tehran", place_id="p1", company_name="Tipax"),
            Branch(name="Vanak", address="Vanak", place_id="p2", company_name="Tipax"),
        ]
        self.reviews = {
            "p1": [
                Review(author="A", text="bad delay", rating=1, external_id="e1", branch_name="HQ"),
                Review(author="B", text="good service", rating=5, external_id="e2", branch_name="HQ"),
            ],
            "p2": [
                Review(author="C", text="ok", rating=3, external_id="e3", branch_name="Vanak"),
            ],
        }
        self.fail_once_for: set[str] = set()
        self._failed: set[str] = set()

    async def discover_branches(self, company_name: str) -> list[Branch]:
        return list(self.branches)

    async def collect_reviews(self, branch: Branch) -> list[Review]:
        key = branch.place_id
        if key in self.fail_once_for and key not in self._failed:
            self._failed.add(key)
            raise RuntimeError("simulated transient failure")
        return list(self.reviews.get(key, []))

    async def close(self) -> None:
        return None


def test_review_fingerprint_dedupe():
    a = Review(author="Ali", text="Hello World", rating=1, external_id="x1")
    b = Review(author="Ali", text="Hello World", rating=1, external_id="x1")
    c = Review(author="Ali", text="Hello World", rating=1, external_id="x2")
    fa = review_fingerprint(a, branch_key="1")
    fb = review_fingerprint(b, branch_key="1")
    fc = review_fingerprint(c, branch_key="1")
    assert fa == fb
    assert is_duplicate_fingerprint({fa}, fb)
    assert fa != fc


def test_incremental_filter():
    reviews = [
        Review(author="A", text="one", rating=1, external_id="e1"),
        Review(author="B", text="two", rating=2, external_id="e2"),
    ]
    new_reviews, existing = filter_incremental_reviews(
        reviews,
        known_external_ids={"e1"},
        known_fingerprints=set(),
        fingerprint_fn=review_fingerprint,
        branch_key="1",
    )
    assert [r.external_id for r in new_reviews] == ["e2"]
    assert [r.external_id for r in existing] == ["e1"]


def test_production_crawler_resume_retry_and_report(tmp_path: Path):
    async def run() -> None:
        db = Database(str(tmp_path / "crawl.db"))
        await db.connect()
        source = FakeSource()
        source.fail_once_for.add("p2")
        monitor = CrawlMonitor()
        crawler = ProductionCrawler(db, source, monitor=monitor)
        config = CrawlConfig(company_name="Tipax", mode="full", max_attempts=3)

        # First run: one branch fails once then should be retried in same run via claim loop.
        # Because fail_once only fails first collect, claim_next will pick failed task again.
        report = await crawler.run(config)
        assert report.branches_succeeded >= 1
        assert report.reviews_new >= 2

        # Incremental second run should update existing and add none if same payload.
        source2 = FakeSource()
        crawler2 = ProductionCrawler(db, source2, monitor=CrawlMonitor())
        report2 = await crawler2.run(CrawlConfig(company_name="Tipax", mode="incremental"))
        assert report2.reviews_new == 0
        assert report2.reviews_updated >= 1

        progress = await crawler2.get_progress(report2.run_id)
        assert progress.total_branches >= 2

        saved = await db.get_crawl_report(report2.run_id)
        assert saved is not None
        assert saved["company_name"] == "Tipax"
        assert monitor.health()["status"] in {"ok", "attention"}
        await db.close()

    asyncio.run(run())


def test_deleted_branch_detection(tmp_path: Path):
    async def run() -> None:
        db = Database(str(tmp_path / "crawl_del.db"))
        await db.connect()
        company_id = await db.upsert_company("Tipax")
        old_id = await db.upsert_branch(
            company_id,
            Branch(name="Old Branch", address="Old Addr", place_id="old", company_name="Tipax"),
        )
        source = FakeSource()
        crawler = ProductionCrawler(db, source, monitor=CrawlMonitor())
        report = await crawler.run(CrawlConfig(company_name="Tipax", mode="full"))
        rows = await db.list_company_branch_rows(company_id)
        old = next(r for r in rows if int(r["id"]) == old_id)
        assert int(old["is_deleted"]) == 1
        assert report.branches_deleted >= 1
        await db.close()

    asyncio.run(run())


def test_scheduler_runs_jobs():
    async def run() -> None:
        scheduler = CrawlScheduler()
        scheduler.add_job(ScheduleSpec(company_name="Tipax", mode="incremental", interval_seconds=0))
        calls: list[str] = []

        async def runner(spec: ScheduleSpec):
            calls.append(spec.company_name)
            return spec.company_name

        await scheduler.run_forever(runner, tick_seconds=0, max_ticks=2)
        assert calls == ["Tipax", "Tipax"]

    asyncio.run(run())
