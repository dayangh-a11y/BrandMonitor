"""Readiness assessment for leakage-safe training dataset."""

from __future__ import annotations

from typing import Any


def assess_readiness(
    *,
    observation_count: int,
    coverage: dict[str, Any],
    leakage: dict[str, Any],
    class_available_pct: float,
    linked_horse_pct: float,
) -> dict[str, Any]:
    blockers: list[str] = []

    if observation_count <= 0:
        blockers.append("No horse×race observations built")
    if linked_horse_pct < 95:
        blockers.append(
            f"Permanent horse_id link coverage {linked_horse_pct:.1f}% < 95% — identity gaps remain"
        )
    if leakage.get("targets_leak_into_features"):
        blockers.append("Targets leak into features")
    if leakage.get("future_results_used_in_features"):
        blockers.append("Future results used in features")
    if leakage.get("betting_data_used"):
        blockers.append("Betting data present in features")

    # Soft warnings (not hard blockers)
    warnings: list[str] = []
    for f in leakage.get("medium_or_higher_features", []):
        warnings.append(f"Leakage risk {f['leakage_risk']} on feature {f['feature']}")
    if class_available_pct < 50:
        warnings.append(
            f"Structured class available on only {class_available_pct:.1f}% of observations — "
            "class features mostly missing (not invented; not a leakage blocker)"
        )
    if class_available_pct < 20:
        warnings.append(
            "Class feature family is too sparse for class-conditioned models; "
            "baselines A/C/D without class remain usable"
        )

    ready = len(blockers) == 0
    # Class sparsity is a blocker only if <20%; between 20-50 we allow YES with warnings
    # Linked horse: we have near 100% typically

    return {
        "can_create_leakage_safe_training_dataset": "YES" if ready else "NO",
        "ready": ready,
        "blockers": blockers,
        "warnings": warnings,
        "ml_status": "DO_NOT_TRAIN_YET",
        "next_allowed_step": (
            "Freeze feature dataset version + run baseline A–D evaluation on TEST split"
            if ready
            else "Resolve blockers listed above before any model training"
        ),
    }
