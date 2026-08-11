#!/usr/bin/env python3
"""Rebuild Race Week → Race Day → Heat → Result hierarchy and recount stats.

Does NOT compute coverage %% and does NOT run enrichment.

Usage:
  export DATABASE_URL=sqlite:////workspace/output/historical/horse_racing.db
  python scripts/rebuild_race_hierarchy.py
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.hierarchy.rebuild import rebuild_hierarchy, write_reports

DEFAULT_DB = Path("/workspace/output/historical/horse_racing.db")
ART = Path("/opt/cursor/artifacts")
DOCS = ROOT / "docs" / "hierarchy"


def resolve_db(path: str | None) -> Path:
    if path:
        return Path(path)
    env = os.environ.get("DATABASE_URL", "")
    if env.startswith("sqlite:///"):
        raw = env.removeprefix("sqlite:///")
        # sqlite:////abs → /abs ; sqlite:///rel → rel
        if env.startswith("sqlite:////"):
            return Path("/" + env.removeprefix("sqlite:////"))
        return Path(raw)
    return DEFAULT_DB


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="Path to horse_racing.db")
    parser.add_argument(
        "--out",
        default=str(DOCS),
        help="Output directory for hierarchy reports",
    )
    args = parser.parse_args()
    db_path = resolve_db(args.db)
    if not db_path.exists():
        print(
            json.dumps(
                {
                    "error": "database_not_found",
                    "path": str(db_path),
                    "message": (
                        "Cannot recalculate hierarchy without the warehouse SQLite file. "
                        "Expected at output/historical/horse_racing.db on the collector VM."
                    ),
                    "invalidated": True,
                    "coverage_announced": False,
                    "enrichment_run": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    conn = sqlite3.connect(str(db_path))
    try:
        stats = rebuild_hierarchy(conn)
    finally:
        conn.close()

    out_dir = Path(args.out)
    paths = write_reports(stats, out_dir)
    ART.mkdir(parents=True, exist_ok=True)
    art_paths = write_reports(stats, ART / "hierarchy")

    summary = {
        "status": "ok",
        "db": str(db_path),
        "overall": stats["overall"],
        "jalali_years": len(stats["by_jalali_year"]),
        "race_day_rows": len(stats["race_days"]),
        "incomplete_links": stats.get("incomplete_links"),
        "reports": {**paths, **{f"artifact_{k}": v for k, v in art_paths.items()}},
        "invalidated_prior_race_eq_heat_reports": True,
        "coverage_announced": False,
        "enrichment_run": False,
        "note": "Heat is never counted as Race Day.",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    (out_dir / "rebuild_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
