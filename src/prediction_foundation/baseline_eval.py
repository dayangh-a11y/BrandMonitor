"""Race-level baseline evaluation on the frozen TEST split.

Produces RANK/SCORE outputs only — never probabilities.
No ML training. No DB mutation (read-only rating join).
"""

from __future__ import annotations

import gzip
import json
import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from src.prediction_foundation.freeze import assert_dataset_matches_freeze, load_freeze

BASELINE_IDS = ("A", "B", "C", "D")


def _v(row: dict[str, Any], name: str) -> Any:
    return row.get(f"{name}__value")


def _missing(row: dict[str, Any], name: str) -> bool:
    return bool(row.get(f"{name}__is_missing", True)) or _v(row, name) is None


def _finish_points(avg: float | None) -> float | None:
    if avg is None:
        return None
    return max(0.0, 100.0 - (float(avg) - 1.0) * 12.0)


def score_A_historical(row: dict[str, Any]) -> float | None:
    parts: list[tuple[float, float]] = []
    hist = _finish_points(_v(row, "career_avg_finish"))
    if hist is not None and not _missing(row, "career_avg_finish"):
        parts.append((hist, 0.45))
    wr = _v(row, "career_win_rate")
    if wr is not None and not _missing(row, "career_win_rate"):
        parts.append((float(wr) * 100.0, 0.30))
    tr = _v(row, "career_top3_rate")
    if tr is not None and not _missing(row, "career_top3_rate"):
        parts.append((float(tr) * 100.0, 0.25))
    if not parts:
        return None
    return sum(v * w for v, w in parts) / sum(w for _, w in parts)


def score_B_rating(row: dict[str, Any]) -> float | None:
    r = row.get("source_rating")
    if r is None:
        return None
    try:
        r = float(r)
    except (TypeError, ValueError):
        return None
    if r <= 0:
        return None
    return r


def score_C_recent_form(row: dict[str, Any]) -> float | None:
    parts: list[tuple[float, float]] = []
    af = _finish_points(_v(row, "avg_finish_last5"))
    if af is not None and not _missing(row, "avg_finish_last5"):
        parts.append((af, 0.45))
    wr = _v(row, "win_rate_last5")
    if wr is not None and not _missing(row, "win_rate_last5"):
        parts.append((float(wr) * 100.0, 0.30))
    # form_trend: positive = improving
    ft = _v(row, "form_trend")
    if ft is not None and not _missing(row, "form_trend"):
        # map roughly [-5,5] → [0,100]
        parts.append((max(0.0, min(100.0, 50.0 + float(ft) * 10.0)), 0.25))
    if not parts:
        # fallback last_finish
        lf = _v(row, "last_finish")
        if lf is not None and not _missing(row, "last_finish"):
            return _finish_points(float(lf))
        return None
    return sum(v * w for v, w in parts) / sum(w for _, w in parts)


def score_D_contextual(row: dict[str, Any]) -> float | None:
    parts: list[tuple[float, float]] = []
    mapping = [
        ("career_avg_finish", 0.18, True),
        ("avg_finish_last5", 0.22, True),
        ("track_win_rate", 0.12, False),
        ("win_rate_same_distance", 0.12, False),
        ("breed_win_rate", 0.08, False),
        ("trainer_win_rate_prior", 0.10, False),
        ("career_win_rate", 0.10, False),
        ("trainer_recent_form", 0.08, True),
    ]
    for name, w, invert_finish in mapping:
        if _missing(row, name):
            continue
        val = _v(row, name)
        if val is None:
            continue
        if invert_finish:
            pts = _finish_points(float(val))
            if pts is None:
                continue
            parts.append((pts, w))
        else:
            parts.append((float(val) * 100.0, w))
    # weight: lighter often better in handicaps — weak signal only if present
    if not _missing(row, "assigned_weight"):
        wt = float(_v(row, "assigned_weight"))
        # center around 56kg → higher score for lower weight slightly
        parts.append((max(0.0, min(100.0, 100.0 - abs(wt - 56.0) * 3.0)), 0.05))
    if not parts:
        return score_A_historical(row)
    return sum(v * w for v, w in parts) / sum(w for _, w in parts)


SCORERS: dict[str, Callable[[dict[str, Any]], float | None]] = {
    "A": score_A_historical,
    "B": score_B_rating,
    "C": score_C_recent_form,
    "D": score_D_contextual,
}

BASELINE_NAMES = {
    "A": "Historical Ranking",
    "B": "Current Race Rating",
    "C": "Recent Form",
    "D": "Contextual Ranking",
}


def coverage_level(row: dict[str, Any]) -> str:
    keys = [
        "career_avg_finish",
        "avg_finish_last5",
        "track_win_rate",
        "win_rate_same_distance",
        "breed_win_rate",
        "trainer_win_rate_prior",
        "assigned_weight",
    ]
    present = sum(1 for k in keys if not _missing(row, k))
    frac = present / len(keys)
    if frac >= 0.7:
        return "HIGH"
    if frac >= 0.4:
        return "MEDIUM"
    return "LOW"


def race_missing_level(rows: list[dict[str, Any]]) -> str:
    """complete vs substantial_missing for a race."""
    levels = [coverage_level(r) for r in rows]
    low = sum(1 for x in levels if x == "LOW")
    if low / max(1, len(levels)) >= 0.5:
        return "substantial_missing"
    if all(x == "HIGH" for x in levels):
        return "complete"
    return "partial"


def load_test_rows(
    dataset_path: Path,
    *,
    db_path: Path,
) -> list[dict[str, Any]]:
    # rating join
    ratings: dict[int, float | None] = {}
    if db_path.exists():
        c = sqlite3.connect(str(db_path))
        for rid, rating in c.execute(
            "SELECT id, source_rating FROM wh_race_results"
        ):
            ratings[int(rid)] = float(rating) if rating is not None else None
        c.close()

    out: list[dict[str, Any]] = []
    with gzip.open(dataset_path, "rt", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row.get("split") != "TEST":
                continue
            rid = int(row["result_id"])
            row["source_rating"] = ratings.get(rid)
            row["coverage_level"] = coverage_level(row)
            out.append(row)
    return out


def group_races(rows: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    races: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        races[int(r["race_id"])].append(r)
    return races


def rank_race(
    horses: list[dict[str, Any]],
    scorer: Callable[[dict[str, Any]], float | None],
) -> list[dict[str, Any]]:
    """Return horses with pred_score and pred_rank (1=best). Missing scores ranked last."""
    scored = []
    for h in horses:
        s = scorer(h)
        scored.append({**h, "pred_score": s})
    # sort: higher score better; None last; tie-break by result_id for stability
    scored.sort(
        key=lambda x: (
            x["pred_score"] is None,
            -(x["pred_score"] if x["pred_score"] is not None else 0.0),
            int(x["result_id"]),
        )
    )
    for i, h in enumerate(scored, 1):
        h["pred_rank"] = i
    return scored


def actual_winner(horses: list[dict[str, Any]]) -> dict[str, Any] | None:
    winners = [
        h
        for h in horses
        if h.get("target__target_finish") == 1 or h.get("target__target_win") == 1
    ]
    if len(winners) == 1:
        return winners[0]
    # fallback: min valid finish
    valid = [
        h
        for h in horses
        if h.get("target__target_finish") is not None and int(h["target__target_finish"]) >= 1
    ]
    if not valid:
        return None
    return min(valid, key=lambda h: int(h["target__target_finish"]))


def spearmans_footrule_like(pred_rank_by_id: dict[int, int], actual_finish_by_id: dict[int, int]) -> float | None:
    """Spearman correlation on horses with valid finishes."""
    ids = [i for i in pred_rank_by_id if i in actual_finish_by_id]
    n = len(ids)
    if n < 2:
        return None
    # convert actual finish to ranks (already finishes)
    pred = [pred_rank_by_id[i] for i in ids]
    act = [actual_finish_by_id[i] for i in ids]
    d2 = sum((p - a) ** 2 for p, a in zip(pred, act))
    return 1.0 - (6.0 * d2) / (n * (n * n - 1))


def ndcg_at_k(pred_order: list[int], actual_finish: dict[int, int], k: int = 3) -> float | None:
    """Graded relevance = max(0, field_n - finish + 1)."""
    if not pred_order:
        return None
    field_n = max(actual_finish.values()) if actual_finish else len(pred_order)

    def rel(hid: int) -> float:
        f = actual_finish.get(hid)
        if f is None or f < 1:
            return 0.0
        return float(max(0, field_n - f + 1))

    dcg = 0.0
    for i, hid in enumerate(pred_order[:k]):
        dcg += rel(hid) / math.log2(i + 2)
    ideal = sorted((rel(h) for h in actual_finish), reverse=True)[:k]
    idcg = sum(r / math.log2(i + 2) for i, r in enumerate(ideal))
    if idcg <= 0:
        return None
    return dcg / idcg


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if n <= 0:
        return None, None
    p = successes / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n)) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def field_bucket(n: int) -> str:
    if n <= 3:
        return "2-3"
    if n <= 6:
        return "4-6"
    if n <= 9:
        return "7-9"
    return "10+"


@dataclass
class RaceEval:
    race_id: int
    race_date: str
    field_size: int
    missing_level: str
    coverage_mode: str
    winner_result_id: int
    winner_horse_id: int | None
    winner_actual_finish: int
    pred_rank_of_winner: int
    predicted_1_result_id: int
    predicted_1_actual_finish: int | None
    predicted_top3_result_ids: list[int]
    winner_hit: bool
    predicted_1_in_top3: bool
    winner_in_predicted_top3: bool
    mrr: float
    ndcg3: float | None
    spearman: float | None


def evaluate_baseline_on_races(
    races: dict[int, list[dict[str, Any]]],
    baseline_id: str,
) -> tuple[list[RaceEval], list[dict[str, Any]]]:
    scorer = SCORERS[baseline_id]
    race_evals: list[RaceEval] = []
    detail_rows: list[dict[str, Any]] = []

    for race_id, horses in races.items():
        # Need identifiable winner and at least 2 horses
        if len(horses) < 2:
            continue
        winner = actual_winner(horses)
        if winner is None:
            continue
        # require valid finishes for ranking correlation subset
        ranked = rank_race(horses, scorer)
        # skip race if ALL scores missing (no signal)
        if all(h["pred_score"] is None for h in ranked):
            continue

        actual_finish = {
            int(h["result_id"]): int(h["target__target_finish"])
            for h in horses
            if h.get("target__target_finish") is not None and int(h["target__target_finish"]) >= 1
        }
        pred_rank = {int(h["result_id"]): int(h["pred_rank"]) for h in ranked}
        pred_order = [int(h["result_id"]) for h in ranked]

        w_rid = int(winner["result_id"])
        w_rank = pred_rank[w_rid]
        top1 = ranked[0]
        top1_finish = actual_finish.get(int(top1["result_id"]))
        top3_ids = pred_order[:3]

        cov_levels = [h["coverage_level"] for h in horses]
        if all(x == "HIGH" for x in cov_levels):
            cov_mode = "HIGH"
        elif sum(1 for x in cov_levels if x == "LOW") >= len(cov_levels) / 2:
            cov_mode = "LOW"
        else:
            cov_mode = "MEDIUM"

        reval = RaceEval(
            race_id=race_id,
            race_date=str(horses[0]["race_date"]),
            field_size=len(horses),
            missing_level=race_missing_level(horses),
            coverage_mode=cov_mode,
            winner_result_id=w_rid,
            winner_horse_id=winner.get("horse_id"),
            winner_actual_finish=1,
            pred_rank_of_winner=w_rank,
            predicted_1_result_id=int(top1["result_id"]),
            predicted_1_actual_finish=top1_finish,
            predicted_top3_result_ids=top3_ids,
            winner_hit=w_rank == 1,
            predicted_1_in_top3=top1_finish is not None and top1_finish <= 3,
            winner_in_predicted_top3=w_rid in top3_ids,
            mrr=1.0 / w_rank,
            ndcg3=ndcg_at_k(pred_order, actual_finish, 3),
            spearman=spearmans_footrule_like(pred_rank, actual_finish),
        )
        race_evals.append(reval)

        for h in ranked:
            detail_rows.append(
                {
                    "baseline": baseline_id,
                    "baseline_name": BASELINE_NAMES[baseline_id],
                    "race_id": race_id,
                    "race_date": reval.race_date,
                    "result_id": int(h["result_id"]),
                    "horse_id": h.get("horse_id"),
                    "pred_score": h["pred_score"],
                    "pred_rank": h["pred_rank"],
                    "actual_finish": h.get("target__target_finish"),
                    "is_winner": int(h["result_id"]) == w_rid,
                    "coverage_level": h["coverage_level"],
                    "field_size": len(horses),
                    "source_rating": h.get("source_rating"),
                }
            )
    return race_evals, detail_rows


def summarize_evals(evals: list[RaceEval]) -> dict[str, Any]:
    n = len(evals)
    if n == 0:
        return {"n_races": 0}
    hits = sum(1 for e in evals if e.winner_hit)
    p1_top3 = sum(1 for e in evals if e.predicted_1_in_top3)
    win_in_top3 = sum(1 for e in evals if e.winner_in_predicted_top3)
    ranks = sorted(e.pred_rank_of_winner for e in evals)
    mid = ranks[n // 2] if n % 2 == 1 else 0.5 * (ranks[n // 2 - 1] + ranks[n // 2])
    ndcgs = [e.ndcg3 for e in evals if e.ndcg3 is not None]
    rhos = [e.spearman for e in evals if e.spearman is not None]
    hit_lo, hit_hi = wilson_interval(hits, n)
    t3_lo, t3_hi = wilson_interval(p1_top3, n)
    cov_lo, cov_hi = wilson_interval(win_in_top3, n)
    return {
        "n_races": n,
        "winner_hit_pct": round(100.0 * hits / n, 2),
        "winner_hit_wilson95": [None if hit_lo is None else round(100 * hit_lo, 2), None if hit_hi is None else round(100 * hit_hi, 2)],
        "winner_top3_pct": round(100.0 * p1_top3 / n, 2),
        "winner_top3_wilson95": [None if t3_lo is None else round(100 * t3_lo, 2), None if t3_hi is None else round(100 * t3_hi, 2)],
        "actual_winner_in_pred_top3_pct": round(100.0 * win_in_top3 / n, 2),
        "actual_winner_in_pred_top3_wilson95": [None if cov_lo is None else round(100 * cov_lo, 2), None if cov_hi is None else round(100 * cov_hi, 2)],
        "mean_winner_rank": round(sum(ranks) / n, 3),
        "median_winner_rank": mid,
        "mrr": round(sum(e.mrr for e in evals) / n, 4),
        "ndcg_at_3": None if not ndcgs else round(sum(ndcgs) / len(ndcgs), 4),
        "spearman_mean": None if not rhos else round(sum(rhos) / len(rhos), 4),
    }


def stratify(evals: list[RaceEval], key_fn: Callable[[RaceEval], str]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[RaceEval]] = defaultdict(list)
    for e in evals:
        buckets[key_fn(e)].append(e)
    return {k: summarize_evals(v) for k, v in sorted(buckets.items())}


def failure_analysis(evals: list[RaceEval], detail_rows: list[dict[str, Any]], top_n: int = 20) -> dict[str, Any]:
    # worst: high pred_rank_of_winner and/or predicted #1 finished poorly
    scored = []
    for e in evals:
        badness = e.pred_rank_of_winner + (0 if e.predicted_1_actual_finish is None else max(0, e.predicted_1_actual_finish - 1))
        scored.append((badness, e))
    scored.sort(key=lambda x: -x[0])
    worst = []
    for badness, e in scored[:top_n]:
        worst.append(
            {
                "race_id": e.race_id,
                "race_date": e.race_date,
                "field_size": e.field_size,
                "coverage_mode": e.coverage_mode,
                "missing_level": e.missing_level,
                "pred_rank_of_winner": e.pred_rank_of_winner,
                "predicted_1_actual_finish": e.predicted_1_actual_finish,
                "winner_horse_id": e.winner_horse_id,
                "predicted_1_result_id": e.predicted_1_result_id,
                "badness_score": badness,
            }
        )

    # systematic patterns among failures (winner rank > field/2)
    fails = [e for e in evals if e.pred_rank_of_winner >= max(3, e.field_size // 2)]
    by_field = defaultdict(int)
    by_cov = defaultdict(int)
    for e in fails:
        by_field[field_bucket(e.field_size)] += 1
        by_cov[e.coverage_mode] += 1

    return {
        "n_failure_races_defined": len(fails),
        "failure_definition": "pred_rank_of_winner >= max(3, field_size//2)",
        "failures_by_field_bucket": dict(by_field),
        "failures_by_coverage": dict(by_cov),
        "top_20_worst": worst,
        "patterns": [
            "Small-sample / debut horses can dominate Recent Form or inflate Contextual scores.",
            "Rating baseline fails when source_rating missing for most of field.",
            "Large fields make Winner Hit harder; Top3 coverage more informative.",
            "LOW coverage races degrade Historical/Contextual signal quality.",
        ],
    }


def compare_baselines(metrics_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for bid, m in metrics_by_id.items():
        rows.append({"baseline": bid, "name": BASELINE_NAMES[bid], **m})

    # Rank by: 1) Winner Top3 Coverage (actual winner in pred top3)
    # 2) Mean Winner Rank (lower better)
    # 3) Winner Hit Rate
    def sort_key(r: dict[str, Any]):
        return (
            -(r.get("actual_winner_in_pred_top3_pct") or 0),
            (r.get("mean_winner_rank") or 999),
            -(r.get("winner_hit_pct") or 0),
        )

    ordered = sorted(rows, key=sort_key)
    for i, r in enumerate(ordered, 1):
        r["baseline_rank"] = i

    best = ordered[0]["baseline"] if ordered else None
    # Material improvement of D vs A/B/C
    d = metrics_by_id.get("D", {})
    others = {k: metrics_by_id[k] for k in ("A", "B", "C") if k in metrics_by_id}

    def materially_better(d_m: dict[str, Any], o_m: dict[str, Any]) -> bool | None:
        # Use Wilson overlap on winner_top3 (predicted#1 in actual top3) and winner-in-top3
        # Require improvement on primary metric without CI overlap, or mean rank better by >=0.15
        d_cov = d_m.get("actual_winner_in_pred_top3_pct")
        o_cov = o_m.get("actual_winner_in_pred_top3_pct")
        if d_cov is None or o_cov is None:
            return None
        d_ci = d_m.get("actual_winner_in_pred_top3_wilson95") or [None, None]
        o_ci = o_m.get("actual_winner_in_pred_top3_wilson95") or [None, None]
        # non-overlapping CI and d higher
        if d_ci[0] is not None and o_ci[1] is not None and d_ci[0] > o_ci[1]:
            return True
        # mean rank improvement
        d_rank = d_m.get("mean_winner_rank")
        o_rank = o_m.get("mean_winner_rank")
        if d_rank is not None and o_rank is not None and (o_rank - d_rank) >= 0.25 and d_cov >= o_cov:
            return True
        if abs((d_cov or 0) - (o_cov or 0)) < 1.0 and abs((d_rank or 0) - (o_rank or 0)) < 0.15:
            return False
        return None

    vs = {k: materially_better(d, m) for k, m in others.items()}
    if any(v is True for v in vs.values()) and all(v is not False for v in vs.values()):
        # need better than ALL of A,B,C
        if all(v is True for v in vs.values()):
            gate = "YES"
        else:
            gate = "UNCLEAR"
    elif all(v is False for v in vs.values()):
        gate = "NO"
    else:
        # check if D is best by sort order with clear margins
        if best == "D":
            # compare to second
            if len(ordered) >= 2:
                second = metrics_by_id[ordered[1]["baseline"]]
                mb = materially_better(d, second)
                gate = "YES" if mb is True else ("NO" if mb is False else "UNCLEAR")
            else:
                gate = "UNCLEAR"
        else:
            gate = "NO"

    return {
        "ordered_baselines": ordered,
        "best_baseline": best,
        "best_baseline_name": BASELINE_NAMES.get(best),
        "D_vs_A_B_C_material": vs,
        "contextual_outperforms_simpler": gate,
        "ml_gate": "DO_NOT_TRAIN_YET" if gate != "YES" else "MAY_PROCEED_AFTER_FAILURE_REVIEW",
        "tradeoffs": [
            "Historical Ranking is stable when careers are long but weak for debuts/recent improvers.",
            "Race Rating depends on source_rating coverage; many TEST rows lack rating.",
            "Recent Form reacts quickly but overfits tiny samples (n<3).",
            "Contextual Ranking blends signals but can still be dominated by sparse track/distance cells.",
        ],
    }


def run_baseline_evaluation(
    *,
    freeze_path: Path | None = None,
    dataset_path: Path | None = None,
    db_path: Path = Path("output/historical/horse_racing.db"),
    out_dir: Path = Path("data/prediction_foundation/baseline_eval"),
) -> dict[str, Any]:
    freeze = load_freeze(freeze_path)
    dataset_path = Path(dataset_path or freeze["dataset_path"])
    assert_dataset_matches_freeze(freeze, dataset_path)

    rows = load_test_rows(dataset_path, db_path=db_path)
    races = group_races(rows)

    # time thirds by unique sorted race dates
    dates = sorted({r[0]["race_date"] for r in races.values()})
    n_dates = len(dates)
    t1 = max(1, n_dates // 3)
    t2 = max(t1 + 1, (2 * n_dates) // 3)
    date_third = {}
    for i, d in enumerate(dates):
        if i < t1:
            date_third[d] = "first_third"
        elif i < t2:
            date_third[d] = "middle_third"
        else:
            date_third[d] = "final_third"

    metrics_by_id: dict[str, dict[str, Any]] = {}
    all_details: list[dict[str, Any]] = []
    evals_by_id: dict[str, list[RaceEval]] = {}
    strata: dict[str, Any] = {}

    for bid in BASELINE_IDS:
        evals, details = evaluate_baseline_on_races(races, bid)
        # annotate time third
        for e in evals:
            setattr(e, "time_third", date_third.get(e.race_date, "unknown"))
        evals_by_id[bid] = evals
        metrics_by_id[bid] = {
            "baseline": bid,
            "baseline_name": BASELINE_NAMES[bid],
            **summarize_evals(evals),
            "stratified": {
                "field_size": stratify(evals, lambda e: field_bucket(e.field_size)),
                "missing_data": stratify(evals, lambda e: e.missing_level),
                "coverage": stratify(evals, lambda e: e.coverage_mode),
                "time_third": stratify(evals, lambda e: date_third.get(e.race_date, "unknown")),
            },
        }
        all_details.extend(details)
        strata[bid] = metrics_by_id[bid]["stratified"]

    comparison = compare_baselines(metrics_by_id)
    best_id = comparison["best_baseline"] or "D"
    failures = failure_analysis(evals_by_id[best_id], [d for d in all_details if d["baseline"] == best_id])

    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = out_dir / "baseline_metrics.json"
    details_path = out_dir / "baseline_race_results.jsonl"
    fail_path = out_dir / "baseline_failure_analysis.json"
    report_md = out_dir / "baseline_report.md"
    summary_txt = out_dir / "PRE_RACE_BASELINE_BENCHMARK.txt"

    payload = {
        "dataset_version": freeze["dataset_version"],
        "dataset_sha256": freeze["dataset_sha256"],
        "frozen_at_utc": freeze["frozen_at_utc"],
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "split": "TEST",
        "test_rows": len(rows),
        "test_races_total": len(races),
        "probability_calibration": "NOT_APPLICABLE — baselines produce SCORE/RANK only",
        "brier_score": None,
        "baselines": metrics_by_id,
        "comparison": comparison,
        "ml_status": "DO_NOT_TRAIN_YET",
        "ml_gate_decision": comparison["ml_gate"],
        "contextual_outperforms_simpler": comparison["contextual_outperforms_simpler"],
    }
    metrics_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with details_path.open("w", encoding="utf-8") as f:
        for row in all_details:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    fail_payload = {
        "best_baseline": best_id,
        "best_baseline_name": BASELINE_NAMES[best_id],
        **failures,
    }
    fail_path.write_text(json.dumps(fail_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md = _render_md(payload, fail_payload)
    report_md.write_text(md, encoding="utf-8")
    summary_txt.write_text(_render_summary(payload, fail_payload), encoding="utf-8")

    # artifacts mirror
    art = Path("/opt/cursor/artifacts/baseline_eval")
    art.mkdir(parents=True, exist_ok=True)
    for p in (metrics_path, details_path, fail_path, report_md, summary_txt):
        (art / p.name).write_bytes(p.read_bytes())

    return payload


def _render_md(payload: dict[str, Any], failures: dict[str, Any]) -> str:
    lines = [
        "# PRE-RACE BASELINE BENCHMARK",
        "",
        f"- Dataset version: `{payload['dataset_version']}`",
        f"- Dataset sha256: `{payload['dataset_sha256']}`",
        f"- Split: **TEST**",
        f"- TEST races (grouped): {payload['test_races_total']}",
        f"- Probability/Brier: **not applicable** (SCORE/RANK only)",
        f"- ML status: **{payload['ml_status']}**",
        "",
        "## Comparison table",
        "",
        "| Baseline | Winner Hit % | Winner Top3 % | Winner in Pred Top3 % | Mean Winner Rank | Median Winner Rank | MRR | NDCG@3 | N races |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for bid in BASELINE_IDS:
        m = payload["baselines"][bid]
        lines.append(
            f"| {bid} {m['baseline_name']} | {m.get('winner_hit_pct')} | {m.get('winner_top3_pct')} | "
            f"{m.get('actual_winner_in_pred_top3_pct')} | {m.get('mean_winner_rank')} | "
            f"{m.get('median_winner_rank')} | {m.get('mrr')} | {m.get('ndcg_at_3')} | {m.get('n_races')} |"
        )
    comp = payload["comparison"]
    lines += [
        "",
        f"**Best baseline:** {comp.get('best_baseline')} ({comp.get('best_baseline_name')})",
        f"**Contextual outperforms simpler?** {comp.get('contextual_outperforms_simpler')}",
        f"**ML gate:** {comp.get('ml_gate')}",
        "",
        "## Tradeoffs",
        "",
    ]
    for t in comp.get("tradeoffs", []):
        lines.append(f"- {t}")
    lines += ["", "## Top 20 failures (best baseline)", ""]
    for i, w in enumerate(failures.get("top_20_worst", []), 1):
        lines.append(
            f"{i}. race_id={w['race_id']} date={w['race_date']} field={w['field_size']} "
            f"winner_pred_rank={w['pred_rank_of_winner']} pred1_finish={w['predicted_1_actual_finish']} "
            f"coverage={w['coverage_mode']}"
        )
    return "\n".join(lines) + "\n"


def _render_summary(payload: dict[str, Any], failures: dict[str, Any]) -> str:
    comp = payload["comparison"]
    lines = [
        "PRE-RACE BASELINE BENCHMARK",
        f"dataset_version: {payload['dataset_version']}",
        f"dataset_sha256: {payload['dataset_sha256']}",
        f"TEST races: {payload['test_races_total']}",
        f"best_baseline: {comp.get('best_baseline')} ({comp.get('best_baseline_name')})",
        f"contextual_outperforms_simpler: {comp.get('contextual_outperforms_simpler')}",
        f"ml_gate: {comp.get('ml_gate')}",
        f"ml_status: DO_NOT_TRAIN_YET",
        "",
        "METRICS",
    ]
    for bid in BASELINE_IDS:
        m = payload["baselines"][bid]
        lines.append(
            f"{bid} {m['baseline_name']}: hit={m.get('winner_hit_pct')} top3={m.get('winner_top3_pct')} "
            f"win_in_top3={m.get('actual_winner_in_pred_top3_pct')} mean_rank={m.get('mean_winner_rank')} "
            f"mrr={m.get('mrr')} ndcg3={m.get('ndcg_at_3')} n={m.get('n_races')}"
        )
    lines += ["", "TOP20 FAILURES"]
    for i, w in enumerate(failures.get("top_20_worst", []), 1):
        lines.append(
            f"{i}. race={w['race_id']} date={w['race_date']} winner_rank={w['pred_rank_of_winner']} "
            f"pred1_finish={w['predicted_1_actual_finish']} field={w['field_size']} cov={w['coverage_mode']}"
        )
    return "\n".join(lines) + "\n"
