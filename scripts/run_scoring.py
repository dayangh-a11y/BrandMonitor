#!/usr/bin/env python3
"""Recalculate score_v1 for companies/branches from review_analyses."""

from __future__ import annotations

import argparse
import asyncio
import json
import os

from core.config import load_settings
from core.db import Database
from core.logging_setup import setup_logging
from scoring.engine import ScoringEngine
from scoring.insights import InsightsGenerator


async def main() -> None:
    settings = load_settings()
    setup_logging(settings)
    parser = argparse.ArgumentParser(description="Run BrandMonitor score_v1")
    parser.add_argument("--db", default=os.getenv("DB_PATH", settings.db_path))
    parser.add_argument("--company-id", type=int, default=None)
    parser.add_argument("--insights", action="store_true", help="Also refresh insights")
    args = parser.parse_args()

    db = Database(args.db)
    await db.connect()
    engine = ScoringEngine(db)
    insights = InsightsGenerator(db)
    try:
        if args.company_id is not None:
            company = await db.get_company(args.company_id)
            result = await engine.score_company(args.company_id)
            payload = {
                "company_id": args.company_id,
                "score": result.score,
                "components": result.components,
            }
            if args.insights and company:
                payload["insights"] = await insights.refresh_company(
                    args.company_id, company_name=company["name"]
                )
        else:
            scored = await engine.score_all_companies()
            if args.insights:
                for row in scored:
                    company = await db.get_company(int(row["company_id"]))
                    await insights.refresh_company(
                        int(row["company_id"]),
                        company_name=(company or {}).get("name") or "",
                    )
            payload = {"scored_companies": scored}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
