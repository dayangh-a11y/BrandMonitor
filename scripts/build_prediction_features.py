#!/usr/bin/env python3
"""Build Prediction Foundation feature dataset (no ML, no DB writes)."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.prediction_foundation.build import build_prediction_foundation


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, default=Path("output/historical/horse_racing.db"))
    p.add_argument("--out", type=Path, default=Path("data/prediction_foundation"))
    p.add_argument("--max-rows", type=int, default=None, help="Optional cap for smoke tests")
    p.add_argument("--skip-full-jsonl", action="store_true")
    args = p.parse_args()

    summary = build_prediction_foundation(
        db_path=args.db,
        out_dir=args.out,
        max_rows=args.max_rows,
        write_full_jsonl=not args.skip_full_jsonl,
    )

    # Mirror reports to artifacts
    art = Path("/opt/cursor/artifacts/prediction_foundation")
    art.mkdir(parents=True, exist_ok=True)
    reports = Path(args.out) / "reports"
    if reports.exists():
        for f in reports.glob("*"):
            shutil.copy2(f, art / f.name)
    datasets = Path(args.out) / "datasets"
    if datasets.exists():
        art_ds = art / "datasets"
        art_ds.mkdir(exist_ok=True)
        for f in datasets.glob("*"):
            # skip copying huge gz if desired — still copy
            shutil.copy2(f, art_ds / f.name)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
