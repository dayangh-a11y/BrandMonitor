from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from ai.taxonomy import (
    CATEGORY_TAXONOMY,
    AnalysisStatusLiteral,
    DeliverySpeedLiteral,
    PricingLiteral,
    QualityLiteral,
    SCHEMA_VERSION,
    SentimentLiteral,
    UrgencyLiteral,
)


class ConfidenceByField(BaseModel):
    sentiment: float = Field(ge=0.0, le=1.0, default=0.0)
    complaint_categories: float = Field(ge=0.0, le=1.0, default=0.0)
    positive_categories: float = Field(ge=0.0, le=1.0, default=0.0)
    delivery_speed: float = Field(ge=0.0, le=1.0, default=0.0)
    customer_service: float = Field(ge=0.0, le=1.0, default=0.0)
    staff_behavior: float = Field(ge=0.0, le=1.0, default=0.0)
    package_damage: float = Field(ge=0.0, le=1.0, default=0.0)
    pricing: float = Field(ge=0.0, le=1.0, default=0.0)
    tracking: float = Field(ge=0.0, le=1.0, default=0.0)
    professionalism: float = Field(ge=0.0, le=1.0, default=0.0)
    mentioned_employees: float = Field(ge=0.0, le=1.0, default=0.0)
    mentioned_city: float = Field(ge=0.0, le=1.0, default=0.0)
    mentioned_branch: float = Field(ge=0.0, le=1.0, default=0.0)


class AnalysisDTO(BaseModel):
    """Structured AI analysis contract for one review."""

    sentiment: SentimentLiteral
    complaint_categories: list[str] = Field(default_factory=list)
    positive_categories: list[str] = Field(default_factory=list)
    delivery_speed: DeliverySpeedLiteral | None = None
    customer_service: QualityLiteral | None = None
    staff_behavior: QualityLiteral | None = None
    package_damage: bool | None = None
    pricing: PricingLiteral | None = None
    tracking: QualityLiteral | None = None
    professionalism: QualityLiteral | None = None
    mentioned_employees: list[str] = Field(default_factory=list)
    mentioned_city: str | None = None
    mentioned_branch: str | None = None
    urgency: UrgencyLiteral = "low"
    evidence_spans: dict[str, Any] = Field(default_factory=dict)
    confidence_overall: float = Field(ge=0.0, le=1.0, default=0.0)
    confidence_by_field: ConfidenceByField = Field(default_factory=ConfidenceByField)
    language: str | None = None
    status: AnalysisStatusLiteral = "succeeded"
    error: str | None = None
    provider: str = "fake"
    model_id: str = "fake-v1"
    prompt_version: str = "v1"
    schema_version: str = SCHEMA_VERSION
    raw_response: dict[str, Any] = Field(default_factory=dict)

    @field_validator("complaint_categories", "positive_categories")
    @classmethod
    def validate_taxonomy(cls, values: list[str]) -> list[str]:
        unknown = sorted({value for value in values if value not in CATEGORY_TAXONOMY})
        if unknown:
            raise ValueError(f"Unknown categories: {unknown}")
        # Preserve order, drop duplicates.
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                ordered.append(value)
        return ordered

    @field_validator("mentioned_employees")
    @classmethod
    def normalize_employees(cls, values: list[str]) -> list[str]:
        cleaned = [item.strip() for item in values if item and item.strip()]
        seen: set[str] = set()
        ordered: list[str] = []
        for item in cleaned:
            key = item.casefold()
            if key not in seen:
                seen.add(key)
                ordered.append(item)
        return ordered

    @model_validator(mode="after")
    def normalize_optional_text(self) -> AnalysisDTO:
        if self.mentioned_city is not None:
            self.mentioned_city = self.mentioned_city.strip() or None
        if self.mentioned_branch is not None:
            self.mentioned_branch = self.mentioned_branch.strip() or None
        return self
