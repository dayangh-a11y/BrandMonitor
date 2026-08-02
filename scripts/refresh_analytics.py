#!/usr/bin/env python3
"""Precompute analytics snapshots for all companies/branches."""

from __future__ import annotations

import argparse
import asyncio
import json
import os

from analytics.service import AnalyticsService
from core.config import load_settings
from core.db import Database
from core.logging_setup import setup_logging


async def main() -> None:
    settings = load_settings()
    setup_logging(settings)
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=os.getenv("DB_PATH", settings.db_path))
    args = parser.parse_args()
    db = Database(args.db)
    await db.connect()
    try:
        result = await AnalyticsService(db).refresh_all()
        print(json.dumps(result, indent=2))
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
