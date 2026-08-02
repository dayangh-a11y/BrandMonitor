from __future__ import annotations

from typing import Literal

# Controlled taxonomy shared by complaint + positive categories.
CATEGORY_TAXONOMY: frozenset[str] = frozenset(
    {
        "delivery_speed",
        "customer_service",
        "staff_behavior",
        "package_damage",
        "pricing",
        "tracking",
        "professionalism",
        "location_access",
        "communication",
        "other",
    }
)

SentimentLiteral = Literal["Positive", "Neutral", "Negative"]
UrgencyLiteral = Literal["low", "medium", "high"]
DeliverySpeedLiteral = Literal["fast", "normal", "slow"]
QualityLiteral = Literal["good", "average", "bad"]
PricingLiteral = Literal["cheap", "fair", "expensive"]
AnalysisStatusLiteral = Literal["pending", "succeeded", "failed", "skipped"]

PROMPT_VERSION = "v1"
SCHEMA_VERSION = "analysis_dto_v1"
