#!/usr/bin/env python3
"""Harvest horse histories and rank fastest horses per breed.

Usage:
  python scripts/build_fastest_horses_by_breed.py
  python scripts/build_fastest_horses_by_breed.py --min-declared-starts 5
  python scripts/build_fastest_horses_by_breed.py --skip-harvest
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.speed.history import (  # noqa: E402
    harvest_many,
    load_harvest,
    load_horse_targets_from_productions,
)
from src.speed.report import build_fastest_report, write_json, write_markdown_report  # noqa: E402

PRODUCTIONS = ROOT / "data" / "breeding" / "productions_harvest.jsonl"
OUT = ROOT / "data" / "speed"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--productions", type=Path, default=PRODUCTIONS)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--min-declared-starts", type=int, default=1)
    ap.add_argument("--skip-harvest", action="store_true")
    ap.add_argument("--top-n", type=int, default=10)
    args = ap.parse_args()

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    harvest_path = out / "history_harvest.jsonl"

    horses = load_horse_targets_from_productions(
        args.productions, min_starts=args.min_declared_starts
    )
    write_json(
        out / "horse_targets.json",
        {
            "count": len(horses),
            "by_breed": {
                b: sum(1 for h in horses if h["blood"] == b)
                for b in ("TURKMEN", "DOKHOON", "THORUGHBREAD", "ARAB")
            },
            "horses": horses,
        },
    )
    print("targets", len(horses), flush=True)

    if not args.skip_harvest:
        stats = harvest_many(
            horses,
            harvest_path,
            workers=args.workers,
            limit=args.limit,
        )
        write_json(out / "history_harvest_stats.json", stats)
        print("harvest_stats", json.dumps(stats, ensure_ascii=False), flush=True)
    else:
        print("skip-harvest; using", harvest_path, flush=True)

    rows = load_harvest(harvest_path)
    report = build_fastest_report(rows, top_n=args.top_n)
    write_json(out / "fastest_horses_by_breed.json", report)
    write_markdown_report(out / "FASTEST_HORSES_BY_BREED_REPORT.md", report)

    print("headlines:", flush=True)
    for h in report.get("headlines") or []:
        print(
            f"  {h['breed']}: {h.get('fastest_horse')} "
            f"{h.get('best_speed_mps')} m/s @ {h.get('best_distance')}m "
            f"({h.get('best_time_fmt')})",
            flush=True,
        )
    print("wrote", out / "FASTEST_HORSES_BY_BREED_REPORT.md", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
