#!/usr/bin/env python3
"""Seed realistic multi-company analytics demo data (Phase 7)."""

from __future__ import annotations

import argparse
import asyncio
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai.adapters.fake import FakeAdapter
from ai.pipeline import AnalysisPipeline
from analytics.service import AnalyticsService
from core.db import Database
from models.branch import Branch
from models.review import Review
from scoring.engine import ScoringEngine
from scoring.insights import InsightsGenerator

COMPANIES = [
    {
        "name": "Tipax",
        "branches": [
            ("Tipax HQ", "Tehran", "Tehran Province", 2.4),
            ("Tipax Vanak", "Tehran", "Tehran Province", 3.2),
            ("Tipax Mashhad", "Mashhad", "Razavi Khorasan", 3.8),
            ("Tipax Isfahan", "Isfahan", "Isfahan Province", 2.9),
        ],
    },
    {
        "name": "Chapar",
        "branches": [
            ("Chapar Center", "Tehran", "Tehran Province", 3.5),
            ("Chapar Shiraz", "Shiraz", "Fars", 4.1),
            ("Chapar Tabriz", "Tabriz", "East Azerbaijan", 3.0),
        ],
    },
]

REVIEW_TEMPLATES = [
    (1.0, "Worst delivery delay and package damage. Tracking never updated."),
    (1.0, "Expensive pricing and awful customer service in the branch."),
    (2.0, "Slow delivery speed and bad professionalism from staff."),
    (2.0, "Package arrived damaged and tracking quality was bad."),
    (3.0, "Average service, normal delivery, fair pricing overall."),
    (3.0, "Neutral experience. Communication was average."),
    (4.0, "Good customer service and helpful staff behavior by Mr Karimi."),
    (4.0, "Fast delivery and good tracking. Professional team."),
    (5.0, "Great service and fast delivery. Excellent professionalism."),
    (5.0, "Cheap pricing and great communication from Ms Rezaei."),
]


async def _seed_company(db: Database, pipeline: AnalysisPipeline, spec: dict, rng: random.Random) -> int:
    company_id = await db.upsert_company(spec["name"], source="analytics_demo")
    branch_ids: list[int] = []
    for name, city, province, rating in spec["branches"]:
        bid = await db.upsert_branch(
            company_id,
            Branch(
                name=name,
                address=f"{province}, {city}",
                rating=rating,
                review_count=0,
                company_name=spec["name"],
                place_id=f"demo-{spec['name'].lower()}-{city.lower()}-{name.lower().replace(' ', '-')}",
                city=city,
                province=province,
            ),
        )
        branch_ids.append(bid)

        # 12–18 reviews per branch across last ~90 days
        n = rng.randint(12, 18)
        for i in range(n):
            rating_val, text = REVIEW_TEMPLATES[rng.randrange(len(REVIEW_TEMPLATES))]
            day = datetime.now(timezone.utc) - timedelta(days=rng.randint(1, 90))
            # Stamp collected_at via raw update after insert for trend realism
            rid = await db.upsert_review(
                bid,
                Review(
                    author=f"user_{spec['name'][:2]}_{bid}_{i}",
                    rating=float(rating_val),
                    text=f"{text} ({city})",
                    published_at=day.date().isoformat(),
                    external_id=f"analytics-{bid}-{i}",
                    branch_name=name,
                    source="analytics_demo",
                    language="en",
                ),
            )
            assert db._conn is not None
            await db._conn.execute(
                "UPDATE reviews SET collected_at = ? WHERE id = ?",
                (day.isoformat(), rid),
            )
            row = await db.get_review_row(rid)
            assert row is not None
            await pipeline.process_review(
                rid,
                Review(
                    author=row["author"],
                    rating=row["rating"],
                    text=row["text"],
                    published_at=row["published_at"],
                    external_id=row["external_id"],
                    branch_name=row["branch_name"],
                    source=row["source"],
                ),
            )
            # Align analyzed_at with collected day for trends
            await db._conn.execute(
                "UPDATE review_analyses SET analyzed_at = ? WHERE review_id = ?",
                (day.isoformat(), rid),
            )
        await db._conn.execute(
            "UPDATE branches SET review_count = ? WHERE id = ?",
            (n, bid),
        )
        await db._conn.commit()

    insights = InsightsGenerator(db)
    engine = ScoringEngine(db)
    await insights.refresh_company(company_id, company_name=spec["name"])
    # Historical scores: write a few older snapshots then current
    for weeks_ago, factor in ((8, 0.85), (4, 0.92), (0, 1.0)):
        result = await engine.score_company(company_id)
        if weeks_ago:
            stamp = (datetime.now(timezone.utc) - timedelta(weeks=weeks_ago)).isoformat()
            assert db._conn is not None
            await db._conn.execute(
                "UPDATE company_scores SET calculated_at = ? WHERE company_id = ? AND id = ("
                "SELECT id FROM company_scores WHERE company_id = ? ORDER BY id DESC LIMIT 1)",
                (stamp, company_id, company_id),
            )
            for bid in branch_ids:
                await db._conn.execute(
                    "UPDATE branch_scores SET calculated_at = ? WHERE branch_id = ? AND id = ("
                    "SELECT id FROM branch_scores WHERE branch_id = ? ORDER BY id DESC LIMIT 1)",
                    (stamp, bid, bid),
                )
            # nudge historical score slightly
            await db._conn.execute(
                "UPDATE company_scores SET score = ? WHERE company_id = ? AND calculated_at = ?",
                (round(result.score * factor, 2), company_id, stamp),
            )
            await db._conn.commit()
        else:
            _ = factor
    return company_id


async def seed(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path)
    await db.connect()
    pipeline = AnalysisPipeline(db, FakeAdapter())
    rng = random.Random(7)
    company_ids = []
    try:
        for spec in COMPANIES:
            cid = await _seed_company(db, pipeline, spec, rng)
            company_ids.append(cid)
        refreshed = await AnalyticsService(db).refresh_all()
        print(
            {
                "db": db_path,
                "companies": company_ids,
                "analytics_snapshots": refreshed,
                "stats": await db.stats(),
            }
        )
    finally:
        await db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/analytics_demo.db")
    args = parser.parse_args()
    asyncio.run(seed(args.db))


if __name__ == "__main__":
    main()
