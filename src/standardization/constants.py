"""Platform-wide constants for the standardization roadmap."""

from __future__ import annotations

PLATFORM_VERSION = "3.0.0"

MODULES: dict[str, dict[str, str]] = {
    "data_quality": {
        "id": "M01",
        "name": "Data Quality",
        "version": "1.0.0",
    },
    "entity_resolution": {
        "id": "M02",
        "name": "Entity Resolution",
        "version": "1.0.0",
    },
    "season_engine": {
        "id": "M03",
        "name": "Season Engine",
        "version": "1.0.0",
    },
    "race_classification": {
        "id": "M04",
        "name": "Race Classification",
        "version": "1.0.0",
    },
    "performance_metrics": {
        "id": "M05",
        "name": "Performance Metrics",
        "version": "2.0.0",
    },
    "ranking_engine": {
        "id": "M06",
        "name": "Ranking Engine",
        "version": "2.0.0",
    },
    "explainability": {
        "id": "M07",
        "name": "Explainability",
        "version": "1.0.0",
    },
    "confidence_engine": {
        "id": "M08",
        "name": "Confidence Engine",
        "version": "1.0.0",
    },
    "question_engine": {
        "id": "M09",
        "name": "Question Engine",
        "version": "1.0.0",
    },
    "validation_engine": {
        "id": "M10",
        "name": "Validation Engine",
        "version": "1.0.0",
    },
    "benchmark_engine": {
        "id": "M11",
        "name": "Benchmark Engine",
        "version": "1.0.0",
    },
    "version_control": {
        "id": "M12",
        "name": "Version Control",
        "version": "1.0.0",
    },
    "audit_log": {
        "id": "M13",
        "name": "Audit Log",
        "version": "1.0.0",
    },
    "feature_store": {
        "id": "M14",
        "name": "Feature Store",
        "version": "1.0.0",
    },
    "ai_readiness": {
        "id": "M15",
        "name": "AI Readiness",
        "version": "1.0.0",
    },
}

# Canonical AI layer names — never mix
AI_LAYERS = (
    "raw",
    "metrics",
    "features",
    "predictions",
    "recommendations",
)

DEFAULT_COUNTRY = "IR"
DEFAULT_MIN_STARTS = 5
