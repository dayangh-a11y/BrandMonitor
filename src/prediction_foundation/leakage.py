"""Leakage audit for prediction foundation features."""

from __future__ import annotations

from typing import Any

from src.prediction_foundation.dictionary import FEATURE_DICTIONARY, TARGET_DICTIONARY


def run_leakage_audit() -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for f in FEATURE_DICTIONARY:
        risk = f.get("leakage_risk", "UNKNOWN")
        if risk in ("MEDIUM", "HIGH") or "MEDIUM" in str(risk):
            findings.append(
                {
                    "feature": f["feature"],
                    "leakage_risk": risk,
                    "note": f.get("missing_behavior"),
                    "mitigation": (
                        "Use only values known at declaration time; "
                        "prefer frozen as-of snapshots for class/age backfills; "
                        "never join on finish_position when building features."
                    ),
                }
            )

    structural_rules = [
        {
            "rule": "TIME_BASED_CUTOFF",
            "description": "All prior histories require (race_date, race_id, result_id) < current key (strict).",
            "status": "ENFORCED_IN_BUILD",
        },
        {
            "rule": "SAME_DAY_MULTI_RACE",
            "description": "Same calendar day is allowed only for earlier race_id/result_id; equal date alone is not sufficient.",
            "status": "ENFORCED_IN_BUILD",
        },
        {
            "rule": "TARGETS_ISOLATED",
            "description": "target_win / target_top3 / target_finish never enter feature formulas",
            "status": "ENFORCED_IN_COMPUTE",
            "targets": [t["target"] for t in TARGET_DICTIONARY],
        },
        {
            "rule": "NO_FUTURE_RACES",
            "description": "Build pipeline must not read races after observation date for that row",
            "status": "ENFORCED_IN_BUILD",
        },
        {
            "rule": "NO_BETTING_DATA",
            "description": "Odds / pools / market prices are excluded from feature sources",
            "status": "POLICY",
        },
        {
            "rule": "NO_RANDOM_SPLIT",
            "description": "Only chronological TRAIN/VALIDATION/TEST",
            "status": "ENFORCED_IN_SPLIT",
        },
        {
            "rule": "FIELD_SIZE_PROXY",
            "description": (
                "field_size from final result cardinality may differ from morning declarations "
                "due to scratches — flagged MEDIUM"
            ),
            "status": "DOCUMENTED",
        },
        {
            "rule": "IDENTITY_ASOF",
            "description": (
                "Permanent horse_id merges/corrections applied today may regroup historical "
                "careers retroactively — identity_confidence flag required"
            ),
            "status": "FLAGGED",
        },
    ]

    return {
        "title": "Leakage Audit — Prediction Foundation",
        "medium_or_higher_features": findings,
        "structural_rules": structural_rules,
        "betting_data_used": False,
        "future_results_used_in_features": False,
        "targets_leak_into_features": False,
    }
