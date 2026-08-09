"""Season ranking rules: eligibility, confidence, separated boards."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

# Configurable default (Rule 1)
MIN_STARTS_DEFAULT = 5
MIN_STARTS_FORM = 3
MIN_STARTS_EARNINGS = 1

ConfidenceLevel = Literal["very_low", "low", "medium", "valid", "high"]


@dataclass(frozen=True, slots=True)
class SampleConfidence:
    starts: int
    level: ConfidenceLevel
    score: float  # 0..100
    label: str


@dataclass(frozen=True, slots=True)
class Qualification:
    qualified: bool
    status: str  # qualified|excluded|insufficient_data
    reason_qualification: str | None
    reason_exclusion: str | None
    confidence: SampleConfidence
    minimum_starts: int


def sample_size_confidence(starts: int) -> SampleConfidence:
    """Rule 6 — sample-size confidence bands."""
    n = max(0, int(starts))
    if n <= 0:
        return SampleConfidence(0, "very_low", 0.0, "no starts")
    if n == 1:
        return SampleConfidence(1, "very_low", 20.0, "1 start → confidence very low")
    if n == 2:
        return SampleConfidence(2, "low", 40.0, "2 starts → confidence low")
    if n <= 4:
        return SampleConfidence(n, "medium", 60.0, f"{n} starts → confidence medium")
    if n <= 9:
        return SampleConfidence(n, "valid", 85.0, f"{n} starts → valid sample")
    return SampleConfidence(n, "high", 95.0, f"{n} starts → high confidence")


def qualify_for_board(
    *,
    starts: int,
    minimum_starts: int,
    board: str,
) -> Qualification:
    conf = sample_size_confidence(starts)
    if starts < minimum_starts:
        return Qualification(
            qualified=False,
            status="excluded",
            reason_qualification=None,
            reason_exclusion=(
                f"starts={starts} < minimum_starts={minimum_starts} "
                f"for board '{board}'"
            ),
            confidence=conf,
            minimum_starts=minimum_starts,
        )
    return Qualification(
        qualified=True,
        status="qualified",
        reason_qualification=(
            f"starts={starts} >= minimum_starts={minimum_starts} "
            f"for board '{board}'; {conf.label}"
        ),
        reason_exclusion=None,
        confidence=conf,
        minimum_starts=minimum_starts,
    )


def season_best_gate(
    *,
    starts_list: list[int],
    minimum_starts: int = MIN_STARTS_DEFAULT,
) -> dict[str, Any]:
    """
    Rule 5 — if every horse has only one race, Season Best is unavailable.
    Also unavailable when nobody meets minimum_starts.
    """
    if not starts_list:
        return {
            "status": "INSUFFICIENT_DATA",
            "message": "INSUFFICIENT DATA",
            "reason": "no horse metrics in season scope",
            "minimum_starts": minimum_starts,
            "horses_total": 0,
            "horses_qualified": 0,
            "max_starts": 0,
        }
    max_starts = max(starts_list)
    if max_starts <= 1:
        return {
            "status": "INSUFFICIENT_DATA",
            "message": "INSUFFICIENT DATA",
            "reason": (
                "all horses have only one race "
                f"(max_starts={max_starts}); cannot select Best Horse of the Season"
            ),
            "minimum_starts": minimum_starts,
            "horses_total": len(starts_list),
            "horses_qualified": 0,
            "max_starts": max_starts,
        }
    qualified = sum(1 for s in starts_list if s >= minimum_starts)
    if qualified == 0:
        return {
            "status": "INSUFFICIENT_DATA",
            "message": "INSUFFICIENT DATA",
            "reason": (
                f"no horse reaches minimum_starts={minimum_starts} "
                f"(max_starts={max_starts})"
            ),
            "minimum_starts": minimum_starts,
            "horses_total": len(starts_list),
            "horses_qualified": 0,
            "max_starts": max_starts,
        }
    return {
        "status": "OK",
        "message": "Season Best ranking available",
        "reason": (
            f"{qualified}/{len(starts_list)} horses meet "
            f"minimum_starts={minimum_starts}"
        ),
        "minimum_starts": minimum_starts,
        "horses_total": len(starts_list),
        "horses_qualified": qualified,
        "max_starts": max_starts,
    }


def qualification_payload(q: Qualification) -> dict[str, Any]:
    return {
        "starts": q.confidence.starts,
        "confidence": q.confidence.level,
        "confidence_score": q.confidence.score,
        "confidence_label": q.confidence.label,
        "qualification_status": q.status,
        "qualified": q.qualified,
        "reason_for_qualification": q.reason_qualification,
        "reason_for_exclusion": q.reason_exclusion,
        "minimum_starts": q.minimum_starts,
    }
