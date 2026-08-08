#!/usr/bin/env python3
"""Harvest asbdavani /productions and rank best sire/dam per breed by progeny value.

Usage:
  python scripts/build_breeding_value_by_breed.py
  python scripts/build_breeding_value_by_breed.py --skip-harvest
  python scripts/build_breeding_value_by_breed.py --limit 50 --min-known-offspring 5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.breeding.productions import (  # noqa: E402
    harvest_many,
    load_harvest,
    load_parent_targets,
)
from src.breeding.report import (  # noqa: E402
    build_breeding_value_report,
    write_json,
    write_markdown_report,
)

ENTITIES = ROOT / "data" / "pedigree" / "pedigree_entities.json"
RELATIONSHIPS = ROOT / "data" / "pedigree" / "pedigree_relationships.jsonl"
OUT = ROOT / "data" / "breeding"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--min-known-offspring", type=int, default=1)
    ap.add_argument("--skip-harvest", action="store_true")
    ap.add_argument("--top-n", type=int, default=10)
    args = ap.parse_args()

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    harvest_path = out / "productions_harvest.jsonl"

    parents = load_parent_targets(ENTITIES, RELATIONSHIPS)
    write_json(
        out / "parent_targets.json",
        {
            "count": len(parents),
            "sires": sum(1 for p in parents if p["role"] == "SIRE"),
            "dams": sum(1 for p in parents if p["role"] == "DAM"),
            "parents": parents,
        },
    )

    if not args.skip_harvest:
        stats = harvest_many(
            parents,
            harvest_path,
            workers=args.workers,
            limit=args.limit,
            min_known_offspring=args.min_known_offspring,
        )
        write_json(out / "productions_harvest_stats.json", stats)
        print("harvest_stats", json.dumps(stats, ensure_ascii=False))
    else:
        print("skip-harvest; using", harvest_path)

    rows = load_harvest(harvest_path)
    report = build_breeding_value_report(rows, top_n=args.top_n)
    write_json(out / "breeding_value_by_breed.json", report)
    write_markdown_report(out / "BREEDING_VALUE_BY_BREED_REPORT.md", report)

    print("headlines:")
    for h in report.get("headlines") or []:
        print(
            f"  {h['breed']}: stallion={h.get('stallion')} (PRV={h.get('stallion_prv')}) | "
            f"mare={h.get('mare')} (PRV={h.get('mare_prv')})"
        )
    print("wrote", out / "BREEDING_VALUE_BY_BREED_REPORT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
