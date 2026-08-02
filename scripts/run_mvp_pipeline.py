#!/usr/bin/env python3
"""
End-to-end MVP pipeline: pending reviews -> AI analysis -> insights -> scores.

Does not change API/UI contracts. Uses FakeAdapter by default (set AI_PROVIDER=openai for live).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os

from ai.factory import build_adapter
from ai.pipeline import AnalysisPipeline
from core.config import load_settings
from core.db import Database
from core.logging_setup import get_logger, setup_logging
from models.review import Review
from scoring.engine import ScoringEngine
from scoring.insights import InsightsGenerator

log = get_logger("api")


async def analyze_pending(db: Database, pipeline: AnalysisPipeline, *, limit: int) -> list[dict]:
    pending = await db.list_pending_review_ids(limit=limit)
    results = []
    for review_id in pending:
        row = await db.get_review_row(review_id)
        if row is None:
            continue
        review = Review(
            author=row["author"] or "",
            rating=float(row["rating"] or 0),
            text=row["text"] or "",
            published_at=row["published_at"] or "",
            language=row["language"] or "",
            external_id=row["external_id"] or "",
            branch_name=row["branch_name"] or "",
            source=row["source"] or "google_maps",
        )
        dto = await pipeline.process_review(review_id, review)
        results.append(
            {
                "review_id": review_id,
                "status": dto.status,
                "sentiment": dto.sentiment,
                "provider": dto.provider,
            }
        )
    return results


async def main() -> None:
    settings = load_settings()
    setup_logging(settings)
    parser = argparse.ArgumentParser(description="BrandMonitor MVP end-to-end pipeline")
    parser.add_argument("--db", default=os.getenv("DB_PATH", settings.db_path))
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--skip-analyze", action="store_true")
    parser.add_argument("--skip-score", action="store_true")
    args = parser.parse_args()

    if args.provider:
        os.environ["AI_PROVIDER"] = args.provider
        settings = load_settings()

    db = Database(args.db)
    await db.connect()
    adapter = build_adapter(settings)
    pipeline = AnalysisPipeline(db, adapter)
    engine = ScoringEngine(db)
    insights = InsightsGenerator(db)

    try:
        analyzed = []
        if not args.skip_analyze:
            analyzed = await analyze_pending(db, pipeline, limit=args.limit)
            log.info("mvp_analyzed count=%s", len(analyzed))

        scored = []
        if not args.skip_score:
            companies = await db.list_companies(limit=100000)
            for company in companies:
                cid = int(company["id"])
                await insights.refresh_company(cid, company_name=company["name"])
                result = await engine.score_company(cid)
                scored.append(
                    {
                        "company_id": cid,
                        "name": company["name"],
                        "score": result.score,
                        "n_branches": len(result.components.get("branch_scores") or {}),
                    }
                )
            log.info("mvp_scored companies=%s", len(scored))

        stats = await db.stats()
        print(
            json.dumps(
                {
                    "analyzed": analyzed,
                    "scored": scored,
                    "stats": stats,
                    "provider": settings.ai_provider,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        close = getattr(adapter, "close", None)
        if close:
            await close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
