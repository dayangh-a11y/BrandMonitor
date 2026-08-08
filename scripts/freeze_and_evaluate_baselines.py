#!/usr/bin/env python3
"""Freeze prediction foundation dataset + evaluate baselines A–D on TEST."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.prediction_foundation.baseline_eval import run_baseline_evaluation
from src.prediction_foundation.freeze import freeze_dataset


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--version", default=None)
    p.add_argument("--force-freeze", action="store_true")
    p.add_argument("--skip-eval", action="store_true")
    args = p.parse_args()

    freeze = freeze_dataset(version=args.version, force=args.force_freeze)
    print(json.dumps({"freeze": freeze}, ensure_ascii=False, indent=2))

    if args.skip_eval:
        return 0

    result = run_baseline_evaluation()
    print(
        json.dumps(
            {
                "dataset_version": result["dataset_version"],
                "test_races_total": result["test_races_total"],
                "comparison": result["comparison"],
                "ml_status": result["ml_status"],
                "per_baseline": {
                    k: {
                        "n_races": v.get("n_races"),
                        "winner_hit_pct": v.get("winner_hit_pct"),
                        "winner_top3_pct": v.get("winner_top3_pct"),
                        "actual_winner_in_pred_top3_pct": v.get("actual_winner_in_pred_top3_pct"),
                        "mean_winner_rank": v.get("mean_winner_rank"),
                        "median_winner_rank": v.get("median_winner_rank"),
                        "mrr": v.get("mrr"),
                        "ndcg_at_3": v.get("ndcg_at_3"),
                    }
                    for k, v in result["baselines"].items()
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
