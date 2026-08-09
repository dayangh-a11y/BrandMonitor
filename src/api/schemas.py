"""Pydantic response models for the prediction API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str
    version: str
    dataset_version: str
    ml_status: str = "DO_NOT_TRAIN_YET"
    dataset_loaded: bool = False
    baseline_default: str = "A"


class HorseRef(BaseModel):
    horse_id: int | None = None
    warehouse_horse_id: int | None = None
    result_id: int | None = None
    horse_name: str | None = None
    split: str | None = None
    coverage_level: str | None = None


class RaceListItem(BaseModel):
    race_id: int
    race_date: str | None = None
    track: str | None = None
    distance: float | int | None = None
    breed: str | None = None
    field_size: int | None = None
    split: str | None = None


class RaceListResponse(BaseModel):
    dataset_version: str
    ml_status: str | None = None
    total: int
    offset: int
    limit: int
    races: list[RaceListItem]


class RaceResponse(BaseModel):
    race_id: int
    dataset_version: str
    race_date: str | None = None
    track: str | None = None
    distance: float | int | None = None
    breed: str | None = None
    race_class: str | None = None
    field_size: int
    split: str | None = None
    data_completeness: str | None = None
    horses: list[HorseRef]


class EvidenceItem(BaseModel):
    metric: str
    value: Any


class PredictionItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    rank: int
    horse_id: int | None = None
    horse_name: str | None = None
    score: float | None = None
    probability: None = Field(
        default=None,
        description="Always null for freeze-backed baselines (SCORE/RANK only).",
    )
    evidence: list[EvidenceItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PredictionResponse(BaseModel):
    race_id: int
    dataset_version: str
    ml_status: str | None = None
    baseline: str | None = None
    baseline_name: str | None = None
    data_completeness: str | None = None
    probability_note: str | None = None
    prediction: list[PredictionItem]


class CompareHorseSide(BaseModel):
    model_config = ConfigDict(extra="allow")

    horse_id: int
    horse_name: str | None = None
    rank: int | None = None
    score: float | None = None
    probability: None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class HorseCompareResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    race_id: int
    dataset_version: str
    ml_status: str | None = None
    baseline: str | None = None
    comparison_type: str = "model_score"
    note: str | None = None
    horse_a: CompareHorseSide
    horse_b: CompareHorseSide
    selected: str | None = None
    selected_horse: CompareHorseSide | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    probability: None = None


class HorseAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    horse_id: int
    horse_name: str | None = None
    dataset_version: str
    ml_status: str | None = None
    observation_count: int
    latest_race_id: int | None = None
    latest_race_date: str | None = None
    latest_features: list[EvidenceItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    appearances: list[dict[str, Any]] = Field(default_factory=list)
    note: str | None = None


class HorseSearchItem(BaseModel):
    horse_id: int
    horse_name: str
    breed: str | None = None
    sex: str | None = None
    birth_year: int | None = None


class HorseSearchResponse(BaseModel):
    query: str
    count: int
    horses: list[HorseSearchItem]
    dataset_version: str | None = None
