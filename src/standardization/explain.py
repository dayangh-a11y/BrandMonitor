"""Module 7 — Explainability.

Every answer must explain: Rule, Formula, Metrics, Rows analyzed,
Confidence, Missing data, Warnings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.standardization.confidence import ConfidenceResult


@dataclass
class Explanation:
    rule: str
    formula: str
    metrics: dict[str, Any]
    rows_analyzed: int
    confidence: ConfidenceResult | dict[str, Any] | None
    missing_data: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    version: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        conf: dict[str, Any] | None
        if isinstance(self.confidence, ConfidenceResult):
            conf = self.confidence.to_dict()
        else:
            conf = self.confidence
        return {
            "rule": self.rule,
            "formula": self.formula,
            "metrics": self.metrics,
            "rows_analyzed": self.rows_analyzed,
            "confidence": conf,
            "missing_data": list(self.missing_data),
            "warnings": list(self.warnings),
            "version": self.version,
            **self.extra,
        }

    def to_text(self) -> str:
        parts = [
            f"Rule: {self.rule}",
            f"Formula: {self.formula}",
            f"Rows analyzed: {self.rows_analyzed}",
        ]
        if self.confidence:
            if isinstance(self.confidence, ConfidenceResult):
                parts.append(
                    f"Confidence: {self.confidence.label} ({self.confidence.score:.1f})"
                )
            elif isinstance(self.confidence, dict):
                parts.append(
                    f"Confidence: {self.confidence.get('confidence_label') or self.confidence.get('confidence')}"
                )
        if self.missing_data:
            parts.append(f"Missing data: {', '.join(self.missing_data)}")
        if self.warnings:
            parts.append(f"Warnings: {'; '.join(self.warnings)}")
        if self.version:
            parts.append(f"Version: {self.version}")
        return " | ".join(parts)


def build_explanation(
    *,
    rule: str,
    formula: str,
    metrics: dict[str, Any] | None = None,
    rows_analyzed: int = 0,
    confidence: ConfidenceResult | dict[str, Any] | None = None,
    missing_data: list[str] | None = None,
    warnings: list[str] | None = None,
    version: str | None = None,
    **extra: Any,
) -> Explanation:
    return Explanation(
        rule=rule,
        formula=formula,
        metrics=metrics or {},
        rows_analyzed=rows_analyzed,
        confidence=confidence,
        missing_data=list(missing_data or []),
        warnings=list(warnings or []),
        version=version,
        extra=dict(extra),
    )
