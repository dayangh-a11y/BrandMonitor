#!/usr/bin/env python3
"""Seed a small end-to-end demo dataset for BrandMonitor UI."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from ai.adapters.fake import FakeAdapter
from ai.pipeline import AnalysisPipeline
from core.db import Database
from models.branch import Branch
from models.review import Review
from scoring.engine import ScoringEngine
from scoring.insights import InsightsGenerator


DEMO_REVIEWS = [
    ("Ali", 1.0, "Worst delivery delay in Tehran. Tracking never updated.", "r-demo-1"),
    ("Sara", 5.0, "Great service and fast delivery by Mr Karimi", "r-demo-2"),
    ("Reza", 2.0, "Package damage and bad customer service in Tehran", "r-demo-3"),
    ("Neda", 4.0, "Good professionalism and helpful staff behavior", "r-demo-4"),
    ("Omar", 1.0, "Expensive pricing and awful tracking support", "r-demo-5"),
]


async def seed(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path)
    await db.connect()
    adapter = FakeAdapter()
    pipeline = AnalysisPipeline(db, adapter)

    try:
        company_id = await db.upsert_company("Tipax", source="demo")
        hq_id = await db.upsert_branch(
            company_id,
            Branch(
                name="Tipax HQ",
                address="Tehran Province, Tehran, Nejatollahi St",
                rating=2.3,
                review_count=len(DEMO_REVIEWS),
                company_name="Tipax",
                place_id="demo-tipax-hq",
            ),
        )
        vanak_id = await db.upsert_branch(
            company_id,
            Branch(
                name="Tipax Vanak",
                address="Tehran, Vanak Square",
                rating=3.1,
                review_count=2,
                company_name="Tipax",
                place_id="demo-tipax-vanak",
            ),
        )

        review_ids: list[int] = []
        for author, rating, text, external_id in DEMO_REVIEWS:
            review_id = await db.upsert_review(
                hq_id,
                Review(
                    author=author,
                    rating=rating,
                    text=text,
                    published_at="1 week ago",
                    external_id=external_id,
                    branch_name="Tipax HQ",
                    source="demo",
                ),
            )
            review_ids.append(review_id)
            row = await db.get_review_row(review_id)
            assert row is not None
            review = Review(
                author=row["author"],
                rating=row["rating"],
                text=row["text"],
                published_at=row["published_at"],
                external_id=row["external_id"],
                branch_name=row["branch_name"],
                source=row["source"],
            )
            await pipeline.process_review(review_id, review)

        # Extra branch reviews
        for author, rating, text, external_id in [
            ("Mina", 4.0, "Good and fast courier experience", "r-vanak-1"),
            ("Hamid", 2.0, "Bad delay near Vanak", "r-vanak-2"),
        ]:
            rid = await db.upsert_review(
                vanak_id,
                Review(
                    author=author,
                    rating=rating,
                    text=text,
                    published_at="3 days ago",
                    external_id=external_id,
                    branch_name="Tipax Vanak",
                    source="demo",
                ),
            )
            row = await db.get_review_row(rid)
            assert row is not None
            await pipeline.process_review(
                rid,
                Review(
                    author=row["author"],
                    rating=row["rating"],
                    text=row["text"],
                    branch_name=row["branch_name"],
                    external_id=row["external_id"],
                    source=row["source"],
                ),
            )

        # Deterministic score_v1 + insights from analyses (no hand-authored scores)
        insights = InsightsGenerator(db)
        engine = ScoringEngine(db)
        await insights.refresh_company(company_id, company_name="Tipax")
        company_score = await engine.score_company(company_id)
        hq_score = await db.get_branch_score(hq_id)
        vanak_score = await db.get_branch_score(vanak_id)

        stats = await db.stats()
        print("Demo seed complete")
        print(f"DB: {db_path}")
        print(f"company_id={company_id} hq_branch_id={hq_id} vanak_branch_id={vanak_id}")
        print(
            {
                "company_score": company_score.score,
                "hq_score": None if hq_score is None else hq_score.get("score"),
                "vanak_score": None if vanak_score is None else vanak_score.get("score"),
            }
        )
        print(stats)
    finally:
        await db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/brandmonitor.db")
    args = parser.parse_args()
    asyncio.run(seed(args.db))


if __name__ == "__main__":
    main()
