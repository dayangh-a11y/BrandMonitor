#!/usr/bin/env python3
"""Batch-analyze pending reviews using configured AI provider."""

from __future__ import annotations

import argparse
import asyncio
import json
import os

from ai.factory import build_adapter
from ai.metrics_ai import AI_METRICS
from ai.pipeline import AnalysisPipeline
from core.config import load_settings
from core.db import Database
from core.logging_setup import get_logger, setup_logging
from models.review import Review

log = get_logger("ai_worker")


async def list_pending_review_ids(db: Database, *, limit: int) -> list[int]:
    assert db._conn is not None
    cursor = await db._conn.execute(
        """
        SELECT r.id
        FROM reviews r
        LEFT JOIN review_analyses a ON a.review_id = r.id
        WHERE a.review_id IS NULL
           OR a.status IN ('failed', 'pending')
        ORDER BY r.id ASC
        LIMIT ?
        """,
        (limit,),
    )
    return [int(row["id"]) for row in await cursor.fetchall()]


async def main() -> None:
    settings = load_settings()
    setup_logging(settings)
    parser = argparse.ArgumentParser(description="Run AI analysis on pending reviews")
    parser.add_argument("--db", default=os.getenv("DB_PATH", settings.db_path))
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--provider", default=None, help="Override AI_PROVIDER (fake|openai)")
    args = parser.parse_args()

    if args.provider:
        os.environ["AI_PROVIDER"] = args.provider
        settings = load_settings()

    db = Database(args.db)
    await db.connect()
    adapter = build_adapter(settings)
    pipeline = AnalysisPipeline(db, adapter)

    try:
        pending = await list_pending_review_ids(db, limit=args.limit)
        log.info("pending_reviews=%s provider=%s", len(pending), settings.ai_provider)
        processed = []
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
            processed.append(
                {
                    "review_id": review_id,
                    "status": dto.status,
                    "sentiment": dto.sentiment,
                    "provider": dto.provider,
                    "model_id": dto.model_id,
                }
            )
        ledger = getattr(adapter, "ledger", None)
        print(
            json.dumps(
                {
                    "processed": len(processed),
                    "items": processed[:20],
                    "metrics": AI_METRICS.snapshot(),
                    "ledger": ledger.summary() if ledger else None,
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
