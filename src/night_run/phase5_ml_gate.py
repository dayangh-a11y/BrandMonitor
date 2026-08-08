"""Phase 5 — ML gate (do not train)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.night_run.paths import NIGHT_DIR, PF_DIR


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_phase5(phase4: dict[str, Any] | None = None) -> dict[str, Any]:
    out = NIGHT_DIR / "phase5_ml_gate"
    out.mkdir(parents=True, exist_ok=True)

    metrics_path = NIGHT_DIR / "phase4_baselines" / "baseline_metrics.json"
    if not metrics_path.exists():
        metrics_path = PF_DIR / "baseline_eval" / "baseline_metrics.json"
    if not metrics_path.exists():
        return {"status": "BLOCKED", "reason": "baseline_metrics.json missing"}

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    baselines = metrics.get("baselines") or {}
    a = baselines.get("A") or {}
    b = baselines.get("B") or {}
    c = baselines.get("C") or {}
    d = baselines.get("D") or {}

    # Material improvement: Contextual must beat ALL of A/B/C on winner_hit with
    # non-overlapping Wilson lower bound vs best simpler upper bound — else NO/UNCLEAR.
    def hit(row: dict) -> float:
        return float(row.get("winner_hit_pct") or 0)

    def wilson(row: dict) -> tuple[float, float] | None:
        w = row.get("winner_hit_wilson95")
        if isinstance(w, (list, tuple)) and len(w) == 2:
            return float(w[0]), float(w[1])
        return None

    simpler_best = max(hit(a), hit(b), hit(c))
    contextual = hit(d)
    d_ci = wilson(d)
    # best simpler CI among A/B/C by hit rate
    best_simple_row = max([a, b, c], key=hit)
    s_ci = wilson(best_simple_row)

    material = False
    clarity = "NO"
    if contextual > simpler_best and d_ci and s_ci:
        # material if contextual lower bound > simpler upper bound
        if d_ci[0] > s_ci[1]:
            material = True
            clarity = "YES"
        else:
            clarity = "UNCLEAR"
    elif contextual > simpler_best:
        clarity = "UNCLEAR"
    else:
        clarity = "NO"

    decision = "DO_NOT_TRAIN" if clarity in ("NO", "UNCLEAR") else "PREPARE_PROPOSAL_ONLY"
    # Even if YES, Night Run rules say do not train yet — only proposal
    ml_status = "DO_NOT_TRAIN"

    gate = {
        "generated_at_utc": _utc_now(),
        "question": (
            "Does Contextual Ranking materially outperform Historical Ranking, "
            "Race Rating and Recent Form?"
        ),
        "answer": clarity,
        "material_outperformance": material,
        "metrics": {
            "A_historical_winner_hit_pct": hit(a),
            "B_race_rating_winner_hit_pct": hit(b),
            "C_recent_form_winner_hit_pct": hit(c),
            "D_contextual_winner_hit_pct": contextual,
            "simpler_best_winner_hit_pct": simpler_best,
            "D_wilson95": d_ci,
            "simpler_best_wilson95": s_ci,
        },
        "decision": decision,
        "ml_status": ml_status,
        "trained": False,
        "rationale": (
            "Contextual does not clearly beat simpler baselines on winner hit "
            "(Wilson CIs overlap or contextual ≤ simpler). Do not train ML."
            if clarity != "YES"
            else "Contextual appears stronger; prepare proposal only — do not train in this run."
        ),
    }

    proposal = {
        "status": "NOT_AUTHORIZED" if clarity != "YES" else "DRAFT_ONLY_DO_NOT_TRAIN",
        "target": "race winner / top3 ranking (not calibrated probability initially)",
        "features": [
            "horse history rates with sample_n/reliability",
            "recent form",
            "distance/track/class/breed context",
            "trainer/owner/weight/field size",
            "pedigree (after DB load + as-of offspring stats)",
        ],
        "leakage_controls": [
            "strict cutoff (race_date, race_id, result_id)",
            "no same-day leakage",
            "no betting features",
            "as-of pedigree offspring only",
        ],
        "split": "chronological 70/15/15 already used in PF freeze",
        "baseline_metrics_ref": str(metrics_path),
        "proposed_model": "regularized gradient boosting ranker OR logistic pairwise — TBD after gate YES",
        "evaluation_metrics": [
            "winner hit",
            "winner in pred top3",
            "MRR",
            "NDCG@3",
            "mean winner rank",
        ],
        "calibration_strategy": "Platt/isotonic only after ranking value proven; never call raw score probability",
        "explainability_strategy": "feature attributions + evidence blocks for Telegram/API",
        "blocked_reason": None if clarity == "YES" else gate["rationale"],
    }

    (out / "ml_gate_decision.json").write_text(
        json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / "ml_proposal.json").write_text(
        json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / "ML_GATE_REPORT.md").write_text(
        "\n".join(
            [
                "# Phase 5 — ML Gate",
                "",
                f"- Answer: **{clarity}**",
                f"- ML STATUS: **`{ml_status}`**",
                f"- Trained: **false**",
                "",
                "## Hits",
                f"- A Historical: {hit(a)}%",
                f"- B Race Rating: {hit(b)}%",
                f"- C Recent Form: {hit(c)}%",
                f"- D Contextual: {contextual}%",
                "",
                gate["rationale"],
                "",
            ]
        ),
        encoding="utf-8",
    )

    return {
        "status": "COMPLETE",
        "phase": 5,
        "answer": clarity,
        "ml_status": ml_status,
        "trained": False,
        "output_dir": str(out),
    }
