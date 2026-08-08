"""Post-race evaluation of a frozen Pre-Race Benchmark.

Separate from the benchmark itself. Never mutates the benchmark file.
Does not treat Relative Score Share as probability.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from src.prerace.benchmark import load_benchmark


def _spearman_rank_corr(pred_ranks: list[int], actual_ranks: list[int]) -> float | None:
    """Spearman correlation for paired ranks (1..n)."""
    n = len(pred_ranks)
    if n < 2 or len(actual_ranks) != n:
        return None
    # ranks already 1..n ideally; compute on given values
    d2 = sum((p - a) ** 2 for p, a in zip(pred_ranks, actual_ranks))
    return 1.0 - (6.0 * d2) / (n * (n * n - 1))


def evaluate_benchmark(
    benchmark: dict[str, Any],
    *,
    actual_finish_order: list[dict[str, Any]],
    evaluated_at_utc: str | None = None,
    race_result_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Evaluate a frozen benchmark against actual finishing order.

    actual_finish_order: list of {horse_id, finish_position} or ordered list
    where index 0 = winner. finish_position is 1-based.
    """
    ts = evaluated_at_utc or datetime.now(timezone.utc).isoformat()

    # Normalize actual order
    if actual_finish_order and "finish_position" in actual_finish_order[0]:
        ordered = sorted(actual_finish_order, key=lambda x: int(x["finish_position"]))
    else:
        ordered = [
            {"horse_id": int(x["horse_id"]), "finish_position": i + 1, **{k: v for k, v in x.items() if k != "horse_id"}}
            for i, x in enumerate(actual_finish_order)
        ]

    actual_by_id = {int(x["horse_id"]): int(x["finish_position"]) for x in ordered}
    winner_id = next(int(x["horse_id"]) for x in ordered if int(x["finish_position"]) == 1)
    top2_actual = {int(x["horse_id"]) for x in ordered if int(x["finish_position"]) <= 2}
    top3_actual = {int(x["horse_id"]) for x in ordered if int(x["finish_position"]) <= 3}

    leans = benchmark["leans"]
    win_lean_id = int(leans["WIN_LEAN"]["horse_id"])
    exacta = leans["EXACTA_LEAN"]
    exacta_first = int(exacta["first"]["horse_id"])
    exacta_second = int(exacta["second"]["horse_id"])
    top3_pred = [int(x["horse_id"]) for x in leans["TOP_3"]]

    winner_hit = win_lean_id == winner_id
    top2_hit = win_lean_id in top2_actual
    top3_hit = set(top3_pred) == top3_actual or (
        # standard top3 hit: all predicted top3 finished in actual top3 (set match)
        set(top3_pred).issubset(top3_actual) and len(top3_pred) == 3
    )
    # Prefer set equality for unordered top-3 hit; also report overlap count
    top3_overlap = len(set(top3_pred) & top3_actual)
    top3_hit = top3_overlap == 3

    # Exacta: predicted 1st and 2nd in exact order
    actual_second = next(
        (int(x["horse_id"]) for x in ordered if int(x["finish_position"]) == 2), None
    )
    exacta_hit = exacta_first == winner_id and exacta_second == actual_second

    # Rank correlation over horses present in both
    horses = benchmark["horses"]
    pred_ranks = []
    act_ranks = []
    paired = []
    for h in horses:
        hid = int(h["horse_id"])
        if hid not in actual_by_id:
            continue
        pred_ranks.append(int(h["rank"]))
        act_ranks.append(actual_by_id[hid])
        paired.append(
            {
                "horse_id": hid,
                "horse": h["horse"],
                "pred_rank": int(h["rank"]),
                "actual_finish": actual_by_id[hid],
            }
        )
    rho = _spearman_rank_corr(pred_ranks, act_ranks)

    # Probabilities intentionally absent
    has_real_probabilities = False
    brier_score = None
    calibration = None

    evaluation = {
        "evaluation_id": f"eval::{benchmark['benchmark_id']}::{ts}",
        "benchmark_id": benchmark["benchmark_id"],
        "benchmark_content_sha256": benchmark.get("content_sha256"),
        "benchmark_frozen_at_utc": benchmark.get("frozen_at_utc"),
        "evaluated_at_utc": ts,
        "race_result_ref": race_result_ref,
        "actual_finish_order": ordered,
        "metrics": {
            "Winner_Hit": bool(winner_hit),
            "Top_2_Hit": bool(top2_hit),
            "Top_3_Hit": bool(top3_hit),
            "Top_3_Overlap": top3_overlap,
            "Exacta_Hit": bool(exacta_hit),
            "Rank_Correlation_Spearman": None if rho is None else round(rho, 4),
            "Brier_Score": brier_score,
            "Calibration": calibration,
        },
        "probability_metrics_status": {
            "Brier_Score": "SKIPPED — no real Prediction Probability in benchmark",
            "Calibration": "SKIPPED — no real Prediction Probability in benchmark",
            "Relative_Score_Share_used_as_probability": False,
        },
        "has_real_probabilities": has_real_probabilities,
        "leans_checked": {
            "WIN_LEAN": leans["WIN_LEAN"],
            "EXACTA_LEAN": leans["EXACTA_LEAN"],
            "TOP_3": leans["TOP_3"],
        },
        "rank_pairs": paired,
        "benchmark_mutated": False,
        "notes": (
            "Evaluation is a separate artifact. The Pre-Race Benchmark remains immutable. "
            "Relative Score Share is not a probability."
        ),
    }
    return evaluation


def write_evaluation(evaluation: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def evaluate_benchmark_file(
    benchmark_path: Path,
    actual_finish_order: list[dict[str, Any]],
    *,
    out_path: Path | None = None,
    race_result_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    benchmark = load_benchmark(benchmark_path)
    evaluation = evaluate_benchmark(
        benchmark,
        actual_finish_order=actual_finish_order,
        race_result_ref=race_result_ref,
    )
    if out_path is not None:
        write_evaluation(evaluation, out_path)
    return evaluation
