#!/usr/bin/env python3
"""Backup / export tools: SQLite copy, CSV, JSON."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from core.config import load_settings
from core.db import Database
from core.logging_setup import get_logger, setup_logging

log = get_logger("ops")


async def export_json(db: Database, out_path: Path) -> Path:
    companies = await db.list_companies(limit=100000)
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "companies": [],
    }
    for company in companies:
        cid = int(company["id"])
        branches = await db.list_company_branches(cid, limit=100000)
        branch_payload = []
        for branch in branches:
            bid = int(branch["id"])
            reviews, _total = await db.list_branch_reviews(bid, limit=100000)
            branch_payload.append({**branch, "reviews": reviews})
        payload["companies"].append({**company, "branches": branch_payload})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


async def export_csv(db: Database, out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    companies = await db.list_companies(limit=100000)
    companies_path = out_dir / "companies.csv"
    branches_path = out_dir / "branches.csv"
    reviews_path = out_dir / "reviews.csv"

    with companies_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["id", "name", "source", "created_at"])
        writer.writeheader()
        for row in companies:
            writer.writerow({k: row.get(k, "") for k in writer.fieldnames})

    all_branches = []
    all_reviews = []
    for company in companies:
        branches = await db.list_company_branches(int(company["id"]), limit=100000)
        for branch in branches:
            all_branches.append(branch)
            reviews, _total = await db.list_branch_reviews(int(branch["id"]), limit=100000)
            all_reviews.extend(reviews)

    branch_fields = [
        "id",
        "company_id",
        "name",
        "address",
        "rating",
        "review_count",
        "maps_url",
        "place_id",
        "collected_at",
    ]
    with branches_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=branch_fields, extrasaction="ignore")
        writer.writeheader()
        for row in all_branches:
            writer.writerow({k: row.get(k, "") for k in branch_fields})

    review_fields = [
        "id",
        "branch_id",
        "author",
        "rating",
        "text",
        "published_at",
        "language",
        "source",
        "external_id",
        "collected_at",
    ]
    with reviews_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=review_fields, extrasaction="ignore")
        writer.writeheader()
        for row in all_reviews:
            writer.writerow({k: row.get(k, "") for k in review_fields})

    return {
        "companies_csv": str(companies_path),
        "branches_csv": str(branches_path),
        "reviews_csv": str(reviews_path),
    }


def export_sqlite(db_path: Path, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_path, out_path)
    return out_path


async def main() -> None:
    settings = load_settings()
    setup_logging(settings)
    parser = argparse.ArgumentParser(description="BrandMonitor backup/export")
    parser.add_argument("--db", default=settings.db_path)
    parser.add_argument("--out-dir", default=settings.backup_dir)
    parser.add_argument(
        "--format",
        choices=["sqlite", "csv", "json", "all"],
        default="all",
    )
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_root = Path(args.out_dir) / stamp
    out_root.mkdir(parents=True, exist_ok=True)
    results: dict[str, object] = {"out_dir": str(out_root)}

    db_path = Path(args.db)
    if args.format in ("sqlite", "all"):
        if not db_path.exists():
            raise SystemExit(f"Database not found: {db_path}")
        sqlite_out = export_sqlite(db_path, out_root / "brandmonitor.db")
        results["sqlite"] = str(sqlite_out)
        log.info("exported_sqlite path=%s", sqlite_out)

    if args.format in ("csv", "json", "all"):
        db = Database(str(db_path))
        await db.connect()
        try:
            if args.format in ("csv", "all"):
                results["csv"] = await export_csv(db, out_root / "csv")
                log.info("exported_csv dir=%s", out_root / "csv")
            if args.format in ("json", "all"):
                json_path = await export_json(db, out_root / "brandmonitor.json")
                results["json"] = str(json_path)
                log.info("exported_json path=%s", json_path)
        finally:
            await db.close()

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
