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

        await db.upsert_company_insights(
            company_id,
            summary=(
                "Tipax shows mixed customer experience. Delivery speed and tracking "
                "are the most frequent complaints, while some customers praise staff "
                "helpfulness and occasional fast deliveries."
            ),
            pros=["staff_behavior", "professionalism", "customer_service"],
            cons=["delivery_speed", "tracking", "package_damage", "pricing"],
            common_categories=["delivery_speed", "tracking", "staff_behavior"],
            review_count_used=7,
        )
        await db.upsert_branch_insights(
            hq_id,
            summary=(
                "Tipax HQ reviews are polarized. Repeated complaints focus on delays, "
                "tracking gaps, and occasional package damage. Positive notes mention "
                "helpful staff and professionalism."
            ),
            pros=["staff_behavior", "professionalism"],
            cons=["delivery_speed", "tracking", "package_damage"],
            common_categories=["delivery_speed", "tracking", "staff_behavior"],
            review_count_used=5,
        )
        await db.upsert_branch_insights(
            vanak_id,
            summary="Vanak branch has limited evidence with mixed speed feedback.",
            pros=["delivery_speed"],
            cons=["delivery_speed"],
            common_categories=["delivery_speed"],
            review_count_used=2,
        )

        hq_components = {
            "algorithm_version": "score_v1",
            "sentiment_score": 46.0,
            "dimension_score": 44.0,
            "complaint_penalty": -8.5,
            "positive_reward": 3.0,
            "urgency_penalty": -1.0,
            "kappa": 0.71,
            "n_eff": 5.0,
            "raw": 58.0,
            "top_complaints": [
                {"category": "delivery_speed", "share": 0.40},
                {"category": "tracking", "share": 0.25},
            ],
            "top_positives": [
                {"category": "staff_behavior", "share": 0.20},
            ],
            "why": [
                "Repeated delay/tracking complaints pulled the score down.",
                "Helpful staff mentions provided a small positive reward.",
                "Moderate review volume keeps confidence medium.",
            ],
        }
        await db.insert_branch_score(hq_id, score=54.5, components=hq_components)
        await db.insert_branch_score(
            vanak_id,
            score=62.0,
            components={
                "algorithm_version": "score_v1",
                "why": ["Limited mixed evidence; slight lean to neutral-positive."],
                "kappa": 0.35,
                "n_eff": 2.0,
            },
        )
        await db.insert_company_score(
            company_id,
            score=56.0,
            components={
                "algorithm_version": "score_v1",
                "branch_scores": {"Tipax HQ": 54.5, "Tipax Vanak": 62.0},
                "why": [
                    "Company score is a credibility-weighted blend of branch scores.",
                    "HQ volume dominates, so company score stays close to HQ.",
                ],
            },
        )

        stats = await db.stats()
        print("Demo seed complete")
        print(f"DB: {db_path}")
        print(f"company_id={company_id} hq_branch_id={hq_id} vanak_branch_id={vanak_id}")
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
