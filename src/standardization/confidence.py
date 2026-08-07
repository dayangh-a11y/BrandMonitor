"""Module 8 — Confidence Engine.

Bands: Very High | High | Medium | Low | Very Low

Depends on sample size, missing values, and data completeness.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ConfidenceBand = Literal["very_high", "high", "medium", "low", "very_low"]

BAND_LABELS: dict[ConfidenceBand, str] = {
    "very_high": "Very High",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
    "very_low": "Very Low",
}


@dataclass(frozen=True, slots=True)
class ConfidenceResult:
    band: ConfidenceBand
    score: float  # 0..100
    label: str
    factors: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence": self.band,
            "confidence_label": self.label,
            "confidence_score": round(self.score, 2),
            "factors": self.factors,
        }


def _sample_component(starts: int) -> tuple[float, str]:
    n = max(0, int(starts))
    if n <= 0:
        return 0.0, "no starts"
    if n == 1:
        return 20.0, "1 start"
    if n == 2:
        return 40.0, "2 starts"
    if n <= 4:
        return 60.0, f"{n} starts"
    if n <= 9:
        return 85.0, f"{n} starts"
    return 95.0, f"{n} starts"


def _missing_component(missing_rate: float) -> tuple[float, str]:
    r = max(0.0, min(1.0, float(missing_rate)))
    score = (1.0 - r) * 100.0
    return score, f"missing_rate={r:.2%}"


def _completeness_component(completeness: float) -> tuple[float, str]:
    c = max(0.0, min(1.0, float(completeness)))
    return c * 100.0, f"completeness={c:.2%}"


def score_to_band(score: float) -> ConfidenceBand:
    if score >= 92:
        return "very_high"
    if score >= 80:
        return "high"
    if score >= 60:
        return "medium"
    if score >= 40:
        return "low"
    return "very_low"


def compute_confidence(
    *,
    starts: int = 0,
    missing_rate: float = 0.0,
    completeness: float = 1.0,
    weights: tuple[float, float, float] = (0.50, 0.25, 0.25),
) -> ConfidenceResult:
    """
    Combined confidence from sample size, missing values, completeness.

    Default weights: sample 50%, missing 25%, completeness 25%.
    Final band is capped by the sample-size band so 1–2 starts can never
    look Highly confident merely because fields are complete.
    """
    s_score, s_note = _sample_component(starts)
    m_score, m_note = _missing_component(missing_rate)
    c_score, c_note = _completeness_component(completeness)
    w_s, w_m, w_c = weights
    total_w = w_s + w_m + w_c
    if total_w <= 0:
        total_w = 1.0
    combined = (w_s * s_score + w_m * m_score + w_c * c_score) / total_w
    # Cap by sample-size ceiling
    sample_cap = {
        0: 15.0,
        1: 35.0,  # very_low max
        2: 55.0,  # low max
    }
    n = max(0, int(starts))
    if n in sample_cap:
        combined = min(combined, sample_cap[n])
    elif n <= 4:
        combined = min(combined, 75.0)  # medium max
    band = score_to_band(combined)
    return ConfidenceResult(
        band=band,
        score=combined,
        label=BAND_LABELS[band],
        factors={
            "sample_size": {"score": s_score, "note": s_note, "starts": starts},
            "missing_values": {"score": m_score, "note": m_note, "missing_rate": missing_rate},
            "data_completeness": {
                "score": c_score,
                "note": c_note,
                "completeness": completeness,
            },
            "weights": {"sample": w_s, "missing": w_m, "completeness": w_c},
            "sample_cap_applied": n <= 4,
        },
    )


def map_legacy_sample_band(level: str) -> ConfidenceBand:
    """Map ranking.py sample bands onto the unified ontology."""
    mapping = {
        "very_low": "very_low",
        "low": "low",
        "medium": "medium",
        "valid": "high",
        "high": "very_high",
    }
    return mapping.get(level, "low")  # type: ignore[return-value]
