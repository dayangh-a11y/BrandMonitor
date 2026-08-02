"""Phase-1 smoke test: collect a few branches + reviews and assert DB write."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from collectors.google_maps.collector import GoogleMapsCollector
from core.csv_exporter import CsvExporter
from core.db import Database


async def run() -> int:
    os.environ.setdefault("HEADLESS", "true")
    os.environ.setdefault("MAX_BRANCHES", "2")
    os.environ.setdefault("MAX_REVIEWS_PER_BRANCH", "10")
    os.environ.setdefault("SCROLL_PAUSE_MS", "1000")

    brand = os.getenv("SEARCH_QUERY", "تیپاکس")
    db_path = "data/smoke_test.db"
    if Path(db_path).exists():
        Path(db_path).unlink()

    collector = GoogleMapsCollector(
        headless=True,
        max_branches=2,
        max_reviews_per_branch=10,
        scroll_pause_ms=1000,
    )
    exporter = CsvExporter()
    db = Database(db_path)

    await db.connect()
    await collector.start()

    try:
        # Capture a screenshot early for debugging if Maps UI changes.
        assert collector.page is not None
        Path("output").mkdir(exist_ok=True)
        await collector.page.screenshot(path="output/smoke_maps_home.png", full_page=True)

        branches, reviews = await collector.collect(brand, with_reviews=True)
        await collector.page.screenshot(path="output/smoke_after_collect.png", full_page=True)

        if not branches:
            print("FAIL: no branches collected")
            return 1

        company_id = await db.upsert_company(brand)
        for branch in branches:
            branch_id = await db.upsert_branch(company_id, branch)
            for review in reviews:
                if review.branch_name == branch.name:
                    await db.upsert_review(branch_id, review)

        exporter.export_branches(branches, filename="output/smoke_branches.csv")
        exporter.export_reviews(reviews, filename="output/smoke_reviews.csv")
        stats = await db.stats()

        print("\n=== SMOKE TEST RESULT ===")
        print(f"branches={len(branches)} reviews={len(reviews)} db={stats}")
        for branch in branches:
            print(f" - {branch.name} | rating={branch.rating} | reviews={branch.review_count}")
        for review in reviews[:5]:
            preview = (review.text[:80] + "...") if len(review.text) > 80 else review.text
            print(f"   * {review.rating} | {review.author} | {preview}")

        # Soft success criteria:
        # - at least 1 branch always required
        # - reviews preferred; if Maps blocks review pane, still keep branch success
        if stats["branches"] < 1:
            print("FAIL: branches not persisted")
            return 1

        if len(reviews) == 0:
            print("WARN: branches OK but zero reviews extracted (Maps UI/consent may have blocked)")
            return 2

        print("PASS")
        return 0
    finally:
        await collector.stop()
        await db.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
