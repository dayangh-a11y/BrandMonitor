"""Phase 4 — baseline backtest packaging (no ML)."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.night_run.paths import NIGHT_DIR, PF_DIR


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_phase4() -> dict[str, Any]:
    out = NIGHT_DIR / "phase4_baselines"
    out.mkdir(parents=True, exist_ok=True)
    src = PF_DIR / "baseline_eval"
    required = [
        "baseline_metrics.json",
        "baseline_race_results.jsonl",
        "baseline_failure_analysis.json",
        "baseline_report.md",
    ]
    missing = [f for f in required if not (src / f).exists()]
    if missing:
        return {
            "status": "BLOCKED",
            "missing": missing,
            "message": "Run scripts/freeze_and_evaluate_baselines.py",
        }

    for f in required:
        shutil.copy2(src / f, out / f)

    metrics = json.loads((out / "baseline_metrics.json").read_text(encoding="utf-8"))
    comparison = metrics.get("comparison") or {}
    best_id = comparison.get("best_baseline")
    baselines = metrics.get("baselines") or {}
    if best_id and best_id in baselines:
        row = baselines[best_id]
        best = {
            "id": best_id,
            "name": row.get("baseline_name") or comparison.get("best_baseline_name"),
            "winner_hit_pct": row.get("winner_hit_pct"),
            "actual_winner_in_pred_top3_pct": row.get("actual_winner_in_pred_top3_pct"),
            "mean_winner_rank": row.get("mean_winner_rank"),
            "mrr": row.get("mrr"),
            "ndcg_at_3": row.get("ndcg_at_3"),
            "n_races": row.get("n_races"),
            "selection": "from baseline_metrics.comparison.best_baseline (composite rank)",
        }
    else:
        best = None
        best_score = -1.0
        for key, row in baselines.items():
            # Composite: prefer winner-in-pred-top3 then MRR then winner hit
            score = (
                float(row.get("actual_winner_in_pred_top3_pct") or 0)
                + 10 * float(row.get("mrr") or 0)
                + float(row.get("winner_hit_pct") or 0)
            )
            if score > best_score:
                best_score = score
                best = {
                    "id": key,
                    "name": row.get("baseline_name"),
                    "winner_hit_pct": row.get("winner_hit_pct"),
                    "actual_winner_in_pred_top3_pct": row.get("actual_winner_in_pred_top3_pct"),
                    "mean_winner_rank": row.get("mean_winner_rank"),
                    "mrr": row.get("mrr"),
                    "ndcg_at_3": row.get("ndcg_at_3"),
                    "n_races": row.get("n_races"),
                    "selection": "fallback composite",
                }

    summary = {
        "status": "COMPLETE",
        "phase": 4,
        "generated_at_utc": _utc_now(),
        "dataset_version": metrics.get("dataset_version"),
        "dataset_sha256": metrics.get("dataset_sha256"),
        "split": metrics.get("split"),
        "probability_calibration": metrics.get("probability_calibration"),
        "best_baseline": best,
        "ml_status": metrics.get("ml_status") or "DO_NOT_TRAIN",
        "contextual_outperforms_simpler": metrics.get("contextual_outperforms_simpler"),
        "comparison": metrics.get("comparison") or metrics.get("ml_gate_decision"),
        "output_dir": str(out),
        "notes": [
            "Race-level evaluation only.",
            "Scores are ranks/scores — NOT calibrated probabilities.",
            "Betting data unused.",
        ],
    }
    (out / "phase4_status.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary
