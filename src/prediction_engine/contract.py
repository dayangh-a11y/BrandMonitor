"""JSON-serializable Prediction Engine contract (no Telegram coupling)."""

from __future__ import annotations

CONTRACT_VERSION = "pe-v1.0.0"

RANK_RACE_OUTPUT_SCHEMA = {
    "type": "object",
    "required": [
        "race_id",
        "as_of_date",
        "race_conditions",
        "horses",
        "top_pick",
        "top_3",
        "alternate",
        "warnings",
        "methodology_version",
    ],
    "properties": {
        "race_id": {"type": "integer"},
        "as_of_date": {"type": "string"},
        "race_conditions": {"type": "object"},
        "horses": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "horse_id",
                    "rank",
                    "score",
                    "confidence",
                    "data_quality",
                    "evidence",
                    "feature_summary",
                ],
            },
        },
        "top_pick": {"type": ["object", "null"]},
        "top_3": {"type": "array"},
        "alternate": {"type": ["object", "null"]},
        "warnings": {"type": "array"},
        "methodology_version": {"type": "string"},
        "provenance": {"type": "object"},
        "timestamp_utc": {"type": "string"},
    },
    "notes": [
        "score is NOT a calibrated probability unless explicitly marked calibrated=true",
        "horse_id is permanent id_horses.horse_id",
        "Telegram is presentation only",
    ],
}
