"""Phase 9 — master night report + status JSON."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from src.night_run.paths import NIGHT_DIR


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_phase9(phase_results: dict[str, Any]) -> dict[str, Any]:
    out = NIGHT_DIR
    out.mkdir(parents=True, exist_ok=True)

    p1 = phase_results.get("phase_1") or {}
    p2 = phase_results.get("phase_2") or {}
    p3 = phase_results.get("phase_3") or {}
    p4 = phase_results.get("phase_4") or {}
    p5 = phase_results.get("phase_5") or {}
    p6 = phase_results.get("phase_6") or {}
    p7 = phase_results.get("phase_7") or {}
    p8 = phase_results.get("phase_8") or {}

    best = (p4.get("best_baseline") or {})
    pedigree_ready = p1.get("status") == "COMPLETE" and float(
        (p1.get("coverage") or {}).get("complete_pedigree_coverage_pct") or 0
    ) >= 90
    baseline_validated = p4.get("status") == "COMPLETE" and bool(best)
    ready_for_ml = False  # explicit gate
    ready_for_telegram = (
        p6.get("smoke_ok")
        and p7.get("contract_ready")
        and p8.get("design_ready")
        and baseline_validated
    )
    # Telegram service not built — READY means engine/API/design ready for bot wiring
    ready_for_telegram_label = "YES" if ready_for_telegram else "NO"

    blockers = []
    if not (p3.get("pedigree_in_features")):
        blockers.append(
            "Pedigree not yet in prediction feature freeze (file foundation ready; needs next PF rebuild after migration review)"
        )
    if p2.get("overall_status") in ("NEEDS_ATTENTION", "WARNINGS"):
        blockers.append(f"Data quality status={p2.get('overall_status')} — review anomalies")
    if p5.get("ml_status") == "DO_NOT_TRAIN":
        blockers.append("ML gate closed — contextual baseline does not materially beat simpler")
    if not p7.get("http_implemented"):
        blockers.append("HTTP API server not implemented (contract only)")
    if not p8.get("telegram_implemented"):
        blockers.append("Telegram bot UI not implemented (by design in this run)")

    status = {
        "generated_at_utc": _utc_now(),
        "phase_1_status": p1.get("status"),
        "phase_2_status": p2.get("status"),
        "phase_3_status": p3.get("status"),
        "phase_4_status": p4.get("status"),
        "phase_5_status": p5.get("status"),
        "phase_6_status": p6.get("status"),
        "phase_7_status": p7.get("status"),
        "phase_8_status": p8.get("status"),
        "READY_FOR_TELEGRAM": ready_for_telegram_label,
        "READY_FOR_ML": "YES" if ready_for_ml else "NO",
        "PEDIGREE_READY": "YES" if pedigree_ready else "NO",
        "BASELINE_VALIDATED": "YES" if baseline_validated else "NO",
        "FINAL_SYSTEM_STATUS": (
            "FOUNDATION_READY_FOR_TELEGRAM_WIRING"
            if ready_for_telegram
            else "FOUNDATION_PARTIAL"
        ),
        "ml_status": p5.get("ml_status") or "DO_NOT_TRAIN",
        "blockers": blockers,
        "phases": phase_results,
    }

    (out / "night_run_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    cov = p1.get("coverage") or {}
    report = f"""# NIGHT RUN FINAL REPORT

- Generated (UTC): `{status['generated_at_utc']}`
- Final system status: **`{status['FINAL_SYSTEM_STATUS']}`**

## Gate summary

| Gate | Value |
|------|-------|
| READY_FOR_TELEGRAM | **{status['READY_FOR_TELEGRAM']}** |
| READY_FOR_ML | **{status['READY_FOR_ML']}** |
| PEDIGREE_READY | **{status['PEDIGREE_READY']}** |
| BASELINE_VALIDATED | **{status['BASELINE_VALIDATED']}** |
| ML STATUS | **`{status['ml_status']}`** |

## 1. Pedigree coverage

- Canonical horses: {cov.get('total_canonical_horses')}
- Sire coverage: {cov.get('sire_coverage_pct')}%
- Dam coverage: {cov.get('dam_coverage_pct')}%
- Complete (both): {cov.get('complete_pedigree_coverage_pct')}%
- Entities: sire={((p1.get('entities') or {}).get('sire'))}, dam={((p1.get('entities') or {}).get('dam'))}

## 2. Pedigree conflicts

- Count: {p1.get('conflicts')}
- Auto-resolved: **no**

## 3. Data quality status

- Overall: **{p2.get('overall_status')}**
- High-severity anomaly groups: {p2.get('high_severity_anomaly_count')}
- Critical coverage gaps: {json.dumps(p2.get('critical_coverage_gaps') or [], ensure_ascii=False)}

## 4. Feature coverage

- Dataset: `{p3.get('dataset_version')}`
- SHA256: `{p3.get('dataset_sha256')}`
- Pedigree in feature freeze: **{p3.get('pedigree_in_features')}**

## 5. Leakage status

- Leakage audit passed: **{p3.get('leakage_audit_passed')}**
- Cutoff: `(race_date, race_id, result_id)`
- Betting data: unused

## 6. Dataset size

- See `phase3_prediction_dataset/prediction_dataset_version.json` and PF freeze counts
- Warehouse results underpin baselines (~32,970 horse×race observations in PF freeze)

## 7. Baseline results

- Best baseline: **{best.get('id')} {best.get('name')}**
- Winner hit: {best.get('winner_hit_pct')}%
- Actual winner in predicted top3: {best.get('actual_winner_in_pred_top3_pct')}%
- Mean winner rank: {best.get('mean_winner_rank')}
- MRR: {best.get('mrr')}
- NDCG@3: {best.get('ndcg_at_3')}
- N races: {best.get('n_races')}

## 8. Best baseline

**{best.get('id')} — {best.get('name')}**

## 9. ML recommendation

- Gate answer: **{p5.get('answer')}**
- Recommendation: **`{p5.get('ml_status')}`** (trained={p5.get('trained')})
- Do not train until Contextual materially beats A/B/C with clear CI separation.

## 10. Prediction engine readiness

- Contract version smoke: **{p6.get('smoke_ok')}**
- Sample race_id: `{p6.get('sample_race_id')}`
- Score ≠ probability

## 11. API readiness

- Contract ready: **{p7.get('contract_ready')}**
- HTTP implemented: **{p7.get('http_implemented')}**

## 12. Telegram readiness

- Design ready: **{p8.get('design_ready')}**
- Bot implemented: **{p8.get('telegram_implemented')}**
- READY_FOR_TELEGRAM means engine+API contract+design are wire-ready, not that a bot ships today.

## 13. Remaining blockers

{chr(10).join('- ' + b for b in blockers) if blockers else '- none'}

## 14. Recommended next action

1. Review pedigree migration proposal; load harvest into DB after approval.
2. Rebuild prediction features including pedigree (as-of offspring only).
3. Implement thin HTTP API wrapping `src/prediction_engine`.
4. Implement Telegram bot as pure presentation client.
5. Keep ML gated (`DO_NOT_TRAIN`) until Contextual clearly wins.

## Phase statuses

| Phase | Status |
|------|--------|
| 1 Pedigree | {p1.get('status')} |
| 2 Data quality | {p2.get('status')} |
| 3 Dataset validation | {p3.get('status')} |
| 4 Baselines | {p4.get('status')} |
| 5 ML gate | {p5.get('status')} |
| 6 Engine contract | {p6.get('status')} |
| 7 API readiness | {p7.get('status')} |
| 8 Telegram design | {p8.get('status')} |

## Artifacts root

`data/night_run/`
"""
    (out / "NIGHT_RUN_FINAL_REPORT.md").write_text(report, encoding="utf-8")
    return status
