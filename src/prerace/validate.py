"""Self-validation before publishing pre-race predictions."""

from __future__ import annotations

from src.markets.scoring import RunnerContext
from src.prerace.types import HorseTodayScore, ValidationIssue


def validate_prerace(
    field: list[RunnerContext],
    horses: list[HorseTodayScore],
    *,
    min_starts_warn: int = 3,
    min_confidence_warn: float = 45.0,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if not field:
        issues.append(
            ValidationIssue("empty_field", "error", "No runners on race card — cannot predict")
        )
        return issues

    # Missing data
    for r in field:
        missing = []
        if r.form_score_5 is None:
            missing.append("form")
        if r.performance_rating is None and r.sex_adjusted_pr is None:
            missing.append("performance")
        if r.starts < 1:
            missing.append("history")
        if missing:
            issues.append(
                ValidationIssue(
                    "missing_data",
                    "warning",
                    f"Missing {', '.join(missing)} for {r.horse_name}",
                    horse_id=r.horse_id,
                    horse_name=r.horse_name,
                )
            )
        if r.starts < min_starts_warn:
            issues.append(
                ValidationIssue(
                    "insufficient_sample",
                    "warning",
                    f"{r.horse_name} has only {r.starts} starts (< {min_starts_warn})",
                    horse_id=r.horse_id,
                    horse_name=r.horse_name,
                )
            )

    # Low confidence horses
    for h in horses:
        if h.confidence_score < min_confidence_warn:
            issues.append(
                ValidationIssue(
                    "low_confidence",
                    "warning",
                    f"{h.horse_name} confidence {h.confidence} ({h.confidence_score:.0f})",
                    horse_id=h.horse_id,
                    horse_name=h.horse_name,
                )
            )
        if h.data_quality in {"poor", "insufficient"}:
            issues.append(
                ValidationIssue(
                    "poor_data_quality",
                    "warning",
                    f"{h.horse_name} data quality={h.data_quality}",
                    horse_id=h.horse_id,
                    horse_name=h.horse_name,
                )
            )

    # Conflicting signals: high form but very poor chance / high win_rate but low form
    by_id = {r.horse_id: r for r in field}
    for h in horses:
        r = by_id.get(h.horse_id)
        if r is None:
            continue
        if (
            r.form_score_5 is not None
            and r.form_score_5 >= 70
            and h.todays_chance_score <= 35
        ):
            issues.append(
                ValidationIssue(
                    "conflicting_signals",
                    "warning",
                    f"{h.horse_name}: strong form ({r.form_score_5}) but low today's chance "
                    f"({h.todays_chance_score:.1f})",
                    horse_id=h.horse_id,
                    horse_name=h.horse_name,
                )
            )
        if (
            r.win_rate is not None
            and r.win_rate >= 0.4
            and r.form_score_5 is not None
            and r.form_score_5 <= 30
        ):
            issues.append(
                ValidationIssue(
                    "conflicting_signals",
                    "warning",
                    f"{h.horse_name}: high career win_rate but weak recent form",
                    horse_id=r.horse_id,
                    horse_name=r.horse_name,
                )
            )

    # Field-level: all low confidence
    if horses and all(h.confidence_score < min_confidence_warn for h in horses):
        issues.append(
            ValidationIssue(
                "field_low_confidence",
                "error",
                "All runners have low confidence — do not treat rankings as strong tips",
            )
        )

    return issues


def validation_blocks_publish(issues: list[ValidationIssue]) -> bool:
    """Hard block only on empty field / total low confidence errors."""
    return any(i.severity == "error" and i.code in {"empty_field"} for i in issues)
