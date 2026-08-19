"""Module 5 — Performance Metrics catalog (mathematical definitions)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    name: str
    symbol: str
    formula: str
    domain: str
    notes: str
    version: str = "2.0.0"
    inputs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "symbol": self.symbol,
            "formula": self.formula,
            "domain": self.domain,
            "notes": self.notes,
            "version": self.version,
            "inputs": list(self.inputs),
        }


METRIC_DEFINITIONS: dict[str, MetricDefinition] = {
    "wins": MetricDefinition(
        name="wins",
        symbol="W",
        formula="W = count(finish_position = 1)",
        domain="integer ≥ 0",
        notes="Count of first-place finishes in scope.",
        inputs=("finish_position",),
    ),
    "seconds": MetricDefinition(
        name="seconds",
        symbol="S2",
        formula="S2 = count(finish_position = 2)",
        domain="integer ≥ 0",
        notes="Count of second-place finishes.",
        inputs=("finish_position",),
    ),
    "thirds": MetricDefinition(
        name="thirds",
        symbol="S3",
        formula="S3 = count(finish_position = 3)",
        domain="integer ≥ 0",
        notes="Count of third-place finishes.",
        inputs=("finish_position",),
    ),
    "top2_rate": MetricDefinition(
        name="top2_rate",
        symbol="T2",
        formula="T2 = count(finish_position ≤ 2) / starts",
        domain="[0, 1] or null if starts=0",
        notes="Share of starts finishing first or second.",
        inputs=("finish_position", "starts"),
    ),
    "top3_rate": MetricDefinition(
        name="top3_rate",
        symbol="T3",
        formula="T3 = count(finish_position ≤ 3) / starts",
        domain="[0, 1] or null if starts=0",
        notes="Podium rate (places).",
        inputs=("finish_position", "starts"),
    ),
    "average_finish": MetricDefinition(
        name="average_finish",
        symbol="AF",
        formula="AF = mean(finish_position) over starts with known position",
        domain="real ≥ 1 or null",
        notes="Lower is better.",
        inputs=("finish_position",),
    ),
    "average_speed": MetricDefinition(
        name="average_speed",
        symbol="AS",
        formula="AS = mean(distance_m / time_s) for starts with valid time",
        domain="m/s or null",
        notes="Requires parseable race time and distance.",
        inputs=("distance", "time_raw"),
    ),
    "best_speed": MetricDefinition(
        name="best_speed",
        symbol="BS",
        formula="BS = max(distance_m / time_s) for starts with valid time",
        domain="m/s or null",
        notes="Peak observed speed in scope.",
        inputs=("distance", "time_raw"),
    ),
    "form": MetricDefinition(
        name="form",
        symbol="F_k",
        formula=(
            "F_k = weighted mean of last k finish scores; "
            "finish_score = max(0, 100 - 12*(pos-1)); "
            "weights decay linearly toward older starts"
        ),
        domain="[0, 100] or null",
        notes="form_score_3 / form_score_5 / form_score_10 variants.",
        inputs=("finish_position",),
    ),
    "consistency": MetricDefinition(
        name="consistency",
        symbol="C",
        formula=(
            "C = 100 * (1 - min(1, pstdev(finish_positions) / max(1, mean(finish)))) "
            "when starts ≥ 2; else null/low-confidence"
        ),
        domain="[0, 100] or null",
        notes="High when finish positions are stable.",
        inputs=("finish_position",),
    ),
    "improvement": MetricDefinition(
        name="improvement",
        symbol="IMP",
        formula="IMP = form_score_recent - form_score_prior (positive = improving)",
        domain="real",
        notes="Trend signal; requires enough starts for both windows.",
        inputs=("form",),
    ),
    "decline": MetricDefinition(
        name="decline",
        symbol="DEC",
        formula="DEC = max(0, -IMP)",
        domain="≥ 0",
        notes="Magnitude of negative form trend.",
        inputs=("improvement",),
    ),
    "performance": MetricDefinition(
        name="performance",
        symbol="PR",
        formula=(
            "PR = 0.18*win_rate*100 + 0.08*second_rate*100 + 0.05*third_rate*100 "
            "+ 0.15*top3_rate*100 + 0.15*avg_finish_map + 0.12*consistency "
            "+ 0.12*difficulty + 0.10*form5 + 0.05*speed_index; "
            "earnings excluded from PR (tie-break only)"
        ),
        domain="[0, 100] approx",
        notes="Season Best primary score. See ranking_engine.md.",
        version="2.0.0",
        inputs=(
            "wins",
            "seconds",
            "thirds",
            "top3_rate",
            "average_finish",
            "consistency",
            "difficulty",
            "form",
            "speed",
        ),
    ),
}


def metric_catalog() -> list[dict[str, Any]]:
    return [m.to_dict() for m in METRIC_DEFINITIONS.values()]


def get_metric(name: str) -> MetricDefinition | None:
    return METRIC_DEFINITIONS.get(name)


def compute_basic_rates(
    *,
    starts: int,
    wins: int,
    seconds: int,
    thirds: int,
) -> dict[str, float | None]:
    """Pure helpers matching catalog formulas (null-safe)."""
    if starts <= 0:
        return {
            "win_rate": None,
            "top2_rate": None,
            "top3_rate": None,
            "second_rate": None,
            "third_rate": None,
        }
    top2 = wins + seconds
    top3 = wins + seconds + thirds
    return {
        "win_rate": wins / starts,
        "second_rate": seconds / starts,
        "third_rate": thirds / starts,
        "top2_rate": top2 / starts,
        "top3_rate": top3 / starts,
    }
