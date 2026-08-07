"""Standard market answer schema (Output Rules)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MarketAnswer:
    """Every market answer must carry these fields — never a bare ranking."""

    market: str
    prediction: Any
    confidence: str
    confidence_score: float
    reasons: list[str] = field(default_factory=list)
    metrics_used: list[str] = field(default_factory=list)
    sample_size: int = 0
    data_quality: str = "unknown"
    applicable_market: str = ""
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "applicable_market": self.applicable_market or self.market,
            "prediction": self.prediction,
            "confidence": self.confidence,
            "confidence_score": round(self.confidence_score, 2),
            "reasons": list(self.reasons),
            "metrics_used": list(self.metrics_used),
            "sample_size": self.sample_size,
            "data_quality": self.data_quality,
            "warnings": list(self.warnings),
            "details": self.details,
            "version": self.version,
        }


def confidence_band(score: float) -> str:
    if score >= 85:
        return "Very High"
    if score >= 70:
        return "High"
    if score >= 50:
        return "Medium"
    if score >= 30:
        return "Low"
    return "Very Low"


def data_quality_label(*, missing_rate: float, sample_size: int) -> str:
    if sample_size <= 0:
        return "insufficient"
    if missing_rate > 0.4:
        return "poor"
    if missing_rate > 0.2:
        return "fair"
    if sample_size < 5:
        return "limited_sample"
    return "good"


def format_market_answer(answer: MarketAnswer) -> str:
    lines = [
        f"=== {answer.applicable_market or answer.market} ===",
        f"Prediction: {answer.prediction}",
        f"Confidence: {answer.confidence} ({answer.confidence_score:.1f})",
        f"Sample size: {answer.sample_size}",
        f"Data quality: {answer.data_quality}",
        f"Metrics used: {', '.join(answer.metrics_used) or '—'}",
    ]
    if answer.reasons:
        lines.append("Reasons:")
        for r in answer.reasons:
            lines.append(f"  - {r}")
    if answer.warnings:
        lines.append("Warnings:")
        for w in answer.warnings:
            lines.append(f"  - {w}")
    return "\n".join(lines)
