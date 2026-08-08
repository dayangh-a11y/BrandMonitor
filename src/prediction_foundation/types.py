"""Shared types for prediction foundation features."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


RELIABILITY_LOW = "LOW"
RELIABILITY_MEDIUM_LOW = "MEDIUM-LOW"
RELIABILITY_MEDIUM = "MEDIUM"
RELIABILITY_HIGH = "HIGH"


def reliability_from_n(n: int | None) -> str | None:
    if n is None:
        return None
    if n < 3:
        return RELIABILITY_LOW
    if n < 5:
        return RELIABILITY_MEDIUM_LOW
    if n < 10:
        return RELIABILITY_MEDIUM
    return RELIABILITY_HIGH


@dataclass
class FeatureCell:
    """Every feature exposes value + missingness + sample depth."""

    value: Any
    is_missing: bool
    sample_n: int | None = None
    reliability: str | None = None
    raw_rate: float | None = None
    smoothed_rate: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def missing_cell() -> FeatureCell:
    return FeatureCell(value=None, is_missing=True, sample_n=0, reliability=RELIABILITY_LOW)


def value_cell(value: Any, *, sample_n: int | None = None) -> FeatureCell:
    if value is None:
        return missing_cell()
    return FeatureCell(
        value=value,
        is_missing=False,
        sample_n=sample_n,
        reliability=reliability_from_n(sample_n) if sample_n is not None else None,
    )


def rate_cell(
    successes: int,
    trials: int,
    *,
    prior_mean: float,
    prior_strength: float = 5.0,
) -> FeatureCell:
    """Raw rate + empirical-Bayes smoothed rate; never invent from empty evidence."""
    if trials <= 0:
        return FeatureCell(
            value=None,
            is_missing=True,
            sample_n=0,
            reliability=RELIABILITY_LOW,
            raw_rate=None,
            smoothed_rate=None,
        )
    raw = successes / trials
    m = prior_strength
    smoothed = (successes + m * prior_mean) / (trials + m)
    return FeatureCell(
        value=smoothed,
        is_missing=False,
        sample_n=trials,
        reliability=reliability_from_n(trials),
        raw_rate=raw,
        smoothed_rate=smoothed,
    )


@dataclass
class ObservationKeys:
    result_id: int
    race_id: int
    horse_id: int | None  # permanent id_horses.horse_id when linked
    warehouse_horse_id: int
    race_date: str
    track: str | None
    distance: int | None
    surface: str | None
    race_name: str | None
    class_code: str | None
    age_category: str | None
    trainer_id: int | None
    owner_id: int | None
    weight: float | None
    field_size: int | None
    finish_position: int | None


@dataclass
class ObservationBundle:
    keys: ObservationKeys
    features: dict[str, FeatureCell] = field(default_factory=dict)
    flags: dict[str, Any] = field(default_factory=dict)
    targets: dict[str, Any] = field(default_factory=dict)
    split: str | None = None

    def to_flat_row(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "result_id": self.keys.result_id,
            "race_id": self.keys.race_id,
            "horse_id": self.keys.horse_id,
            "warehouse_horse_id": self.keys.warehouse_horse_id,
            "race_date": self.keys.race_date,
            "split": self.split,
        }
        for name, cell in self.features.items():
            row[f"{name}__value"] = cell.value
            row[f"{name}__is_missing"] = cell.is_missing
            row[f"{name}__sample_n"] = cell.sample_n
            row[f"{name}__reliability"] = cell.reliability
            if cell.raw_rate is not None or cell.smoothed_rate is not None:
                row[f"{name}__raw_rate"] = cell.raw_rate
                row[f"{name}__smoothed_rate"] = cell.smoothed_rate
        for k, v in self.flags.items():
            row[f"flag__{k}"] = v
        for k, v in self.targets.items():
            row[f"target__{k}"] = v
        return row
