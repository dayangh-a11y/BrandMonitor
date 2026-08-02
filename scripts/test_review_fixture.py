"""Prove review extraction + DB persistence against a local Maps-like fixture."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from collectors.google_maps.collector import GoogleMapsCollector
from core.db import Database
from models.branch import Branch


async def run() -> int:
    fixture = (ROOT / "tests/fixtures/maps_reviews.html").resolve().as_uri()
    db_path = ROOT / "data/fixture_reviews.db"
    if db_path.exists():
        db_path.unlink()

    collector = GoogleMapsCollector(headless=True, max_reviews_per_branch=10)
    db = Database(str(db_path))
    await db.connect()
    await collector.start()

    try:
        assert collector.page is not None
        await collector.page.goto(fixture, wait_until="domcontentloaded")
        branch = Branch(
            name="تیپاکس شعبه تست",
            rating=3.8,
            review_count=3,
            address="تهران",
            company_name="تیپاکس",
        )
        reviews = await collector._parse_visible_reviews(branch_name=branch.name)
        company_id = await db.upsert_company("تیپاکس")
        branch_id = await db.upsert_branch(company_id, branch)
        for review in reviews:
            await db.upsert_review(branch_id, review)

        stats = await db.stats()
        print("=== FIXTURE REVIEW TEST ===")
        print(f"reviews_extracted={len(reviews)} db={stats}")
        for review in reviews:
            print(f" - {review.rating} | {review.author} | {review.text[:60]}")

        if len(reviews) < 3 or stats["reviews"] < 3:
            print("FAIL")
            return 1
        print("PASS")
        return 0
    finally:
        await collector.stop()
        await db.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
