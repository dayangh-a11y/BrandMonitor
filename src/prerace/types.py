"""Shared types for pre-race intelligence."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Contribution:
    metric: str
    value: Any
    weight: float
    impact: float  # signed contribution to score
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "value": self.value,
            "weight": round(self.weight, 4),
            "impact": round(self.impact, 4),
            "note": self.note,
        }


@dataclass
class Explanation:
    why: str
    contributions: list[Contribution] = field(default_factory=list)
    confidence: str = "Low"
    confidence_score: float = 0.0
    sample_size: int = 0
    data_quality: str = "unknown"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "why": self.why,
            "metrics_contributed": [c.to_dict() for c in self.contributions],
            "confidence": self.confidence,
            "confidence_score": round(self.confidence_score, 2),
            "sample_size": self.sample_size,
            "data_quality": self.data_quality,
            "warnings": list(self.warnings),
        }


@dataclass
class ValidationIssue:
    code: str
    severity: str  # error|warning|info
    message: str
    horse_id: int | None = None
    horse_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "horse_id": self.horse_id,
            "horse_name": self.horse_name,
        }


@dataclass
class RaceContextScore:
    race_strength: float
    field_strength: float
    competition_level: float
    weather_impact: float
    track_suitability: float  # mean suitability across field
    expected_pace: str
    race_shape: str
    explain: Explanation

    def to_dict(self) -> dict[str, Any]:
        return {
            "race_strength": round(self.race_strength, 3),
            "field_strength": round(self.field_strength, 3),
            "competition_level": round(self.competition_level, 3),
            "weather_impact": round(self.weather_impact, 3),
            "track_suitability": round(self.track_suitability, 3),
            "expected_pace": self.expected_pace,
            "race_shape": self.race_shape,
            "explanation": self.explain.to_dict(),
        }


@dataclass
class HorseTodayScore:
    horse_id: int
    horse_name: str
    todays_chance_score: float
    winning_probability: float
    top2_probability: float
    top3_probability: float
    distance_suitability: float | None
    track_suitability: float | None
    weather_suitability: float | None
    recent_form: float | None
    momentum: float | None
    consistency: float | None
    risk_score: float | None
    reliability: float | None
    fatigue: float | None
    rest_condition: float | None
    trainer_form: float | None
    jockey_form: float | None
    horse_jockey_combination: float | None
    horse_trainer_combination: float | None
    opponent_difficulty: float | None
    expected_finish_position: float
    confidence: str
    confidence_score: float
    sample_size: int
    data_quality: str
    h2h_probs: dict[str, float] = field(default_factory=dict)
    explain: Explanation | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "horse_id": self.horse_id,
            "horse": self.horse_name,
            "todays_chance_score": round(self.todays_chance_score, 3),
            "winning_probability": round(self.winning_probability, 4),
            "top2_probability": round(self.top2_probability, 4),
            "top3_probability": round(self.top3_probability, 4),
            "head_to_head_probabilities": self.h2h_probs,
            "distance_suitability": self.distance_suitability,
            "track_suitability": self.track_suitability,
            "weather_suitability": self.weather_suitability,
            "recent_form": self.recent_form,
            "momentum": self.momentum,
            "consistency": self.consistency,
            "risk_score": self.risk_score,
            "reliability": self.reliability,
            "fatigue": self.fatigue,
            "rest_condition": self.rest_condition,
            "trainer_form": self.trainer_form,
            "jockey_form": self.jockey_form,
            "horse_jockey_combination": self.horse_jockey_combination,
            "horse_trainer_combination": self.horse_trainer_combination,
            "opponent_difficulty": self.opponent_difficulty,
            "expected_finish_position": round(self.expected_finish_position, 3),
            "confidence": self.confidence,
            "confidence_score": round(self.confidence_score, 2),
            "sample_size": self.sample_size,
            "data_quality": self.data_quality,
            "explanation": self.explain.to_dict() if self.explain else None,
            "extras": self.extras,
        }
