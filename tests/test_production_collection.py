from __future__ import annotations

import asyncio
import time
from pathlib import Path

from collectors.company_config import list_enabled_companies, load_company_config
from collectors.crawl_models import CrawlConfig
from collectors.dedupe import review_content_hash, review_fingerprint, review_fingerprints_multi
from collectors.google_maps.production_crawler import ProductionCrawler
from collectors.incremental import diff_reviews
from collectors.monitoring import CrawlMonitor
from collectors.sources.registry import build_source
from core.db import Database
from models.branch import Branch
from models.review import Review


class FakeSource:
    def __init__(self):
        self.branches = [
            Branch(
                name="HQ",
                address="Tehran, Iran",
                place_id="p1",
                company_name="Tipax",
                phone="+9821",
                latitude=35.7,
                longitude=51.4,
                city="Tehran",
                province="Tehran",
            ),
            Branch(
                name="Vanak",
                address="Vanak, Tehran",
                place_id="p2",
                company_name="Tipax",
                city="Tehran",
                province="Tehran",
            ),
        ]
        self.reviews = {
            "p1": [
                Review(
                    author="A",
                    text="bad delay",
                    rating=1,
                    external_id="e1",
                    branch_name="HQ",
                    owner_response="sorry",
                    owner_response_at="1 day ago",
                    language="en",
                ),
                Review(
                    author="B",
                    text="good service",
                    rating=5,
                    external_id="e2",
                    branch_name="HQ",
                    language="en",
                ),
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


def test_company_config_not_hardcoded():
    companies, defaults = load_company_config()
    names = {c.name for c in companies}
    assert "Tipax" in names and "Chapar" in names
    assert defaults.mode == "incremental"
    enabled = list_enabled_companies()
    assert all(c.enabled for c in enabled)
    assert "TipaxBox" not in {c.name for c in enabled}


def test_multi_strategy_dedupe_and_content_hash():
    a = Review(author="Ali", text="Hello", rating=1, external_id="x1", published_at="d1")
    b = Review(author="Ali", text="Hello edited", rating=1, external_id="x1", published_at="d1")
    fps = review_fingerprints_multi(a, branch_key="1")
    assert set(fps) >= {"external_id", "author_date_text", "content", "auto"}
    assert review_fingerprint(a, branch_key="1") == review_fingerprint(b, branch_key="1")
    assert review_content_hash(a) != review_content_hash(b)


def test_diff_detects_new_edited_deleted():
    known_ext = {"e1"}
    known_fp = set()
    known_hashes = {"e1": review_content_hash(Review(text="old", rating=1, external_id="e1"))}
    active = [{"id": 9, "key": "e9", "external_id": "e9"}]
    incoming = [
        Review(text="new text", rating=2, external_id="e2"),
        Review(text="changed", rating=1, external_id="e1"),
    ]
    for r in incoming:
        r.content_hash = review_content_hash(r)
    diff = diff_reviews(
        incoming,
        known_external_ids=known_ext,
        known_fingerprints=known_fp,
        known_content_hashes=known_hashes,
        active_rows=active,
        branch_key="1",
    )
    assert [r.external_id for r in diff.new_reviews] == ["e2"]
    assert [r.external_id for r in diff.edited_reviews] == ["e1"]
    assert diff.deleted_review_ids == [9]


def test_production_collection_resume_incremental_deleted(tmp_path: Path):
    async def run() -> None:
        db = Database(str(tmp_path / "prodcol.db"))
        await db.connect()
        source = FakeSource()
        source.fail_once_for.add("p2")
        crawler = ProductionCrawler(db, source, monitor=CrawlMonitor())
        report = await crawler.run(
            CrawlConfig(company_name="Tipax", mode="incremental", max_attempts=3)
        )
        assert report.reviews_new >= 2
        assert report.branches_succeeded >= 1

        # Metadata persisted
        rows = await db.list_company_branch_rows(await db.upsert_company("Tipax"))
        hq = next(r for r in rows if r["name"] == "HQ")
        assert hq.get("phone") == "+9821"
        assert hq.get("city") == "Tehran"
        assert hq.get("last_success_at")

        # Edit + delete path
        source2 = FakeSource()
        source2.reviews["p1"] = [
            Review(
                author="A",
                text="bad delay EDITED",
                rating=1,
                external_id="e1",
                branch_name="HQ",
                owner_response="sorry",
                language="en",
            ),
            # e2 removed => deleted
        ]
        crawler2 = ProductionCrawler(db, source2, monitor=CrawlMonitor())
        report2 = await crawler2.run(
            CrawlConfig(company_name="Tipax", mode="incremental", max_attempts=1)
        )
        assert report2.reviews_updated >= 1
        assert report2.reviews_deleted >= 1

        # One-branch mode
        source3 = FakeSource()
        crawler3 = ProductionCrawler(db, source3, monitor=CrawlMonitor())
        report3 = await crawler3.run(
            CrawlConfig(
                company_name="Tipax",
                mode="incremental",
                branch_place_id="p1",
                max_attempts=1,
            )
        )
        assert report3.branches_succeeded >= 1
        await db.close()

    asyncio.run(run())


def test_source_registry_google_maps():
    source = build_source("google_maps", headless=True, max_branches=1)
    assert source is not None


def test_batch_stress_and_schema(tmp_path: Path):
    async def run() -> None:
        db = Database(str(tmp_path / "batch.db"))
        await db.connect()
        cid = await db.upsert_company("Bulk")
        bid = await db.upsert_branch(
            cid,
            Branch(
                name="B",
                address="Tehran",
                company_name="Bulk",
                phone="1",
                latitude=1.0,
                longitude=2.0,
                city="Tehran",
                province="Tehran",
            ),
        )
        reviews = [
            Review(
                author=f"u{i}",
                text=f"text {i}",
                rating=float((i % 5) + 1),
                external_id=f"x{i}",
                language="en",
            )
            for i in range(5000)
        ]
        t0 = time.perf_counter()
        written = await db.upsert_reviews_batch(bid, reviews)
        elapsed = time.perf_counter() - t0
        assert written == 5000
        assert elapsed < 30
        stats = await db.stats()
        assert stats["reviews"] == 5000
        await db.close()

    asyncio.run(run())
