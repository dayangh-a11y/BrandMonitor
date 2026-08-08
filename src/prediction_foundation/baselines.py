"""Baseline benchmarks to beat later (definitions only — no ML training)."""

from __future__ import annotations

from typing import Any


BASELINES: list[dict[str, Any]] = [
    {
        "id": "A",
        "name": "Current historical ranking",
        "description": (
            "Career/historical finish-based score with recency weighting "
            "(PRE-RACE HISTORICAL ranking methodology)."
        ),
        "inputs": ["career_*", "recent_form_*"],
        "status": "DEFINED_NOT_TRAINED",
    },
    {
        "id": "B",
        "name": "Current race rating",
        "description": "Rank horses by card/source rating when available.",
        "inputs": ["assigned_weight optional", "external card rating — not yet a warehouse feature"],
        "status": "DEFINED_NOT_TRAINED",
        "blocker": "Source rating on entries is available as source_rating; not yet in feature dict as rating feature",
    },
    {
        "id": "C",
        "name": "Recent-form ranking",
        "description": "Rank by avg_finish_last5 / win_rate_last5 only.",
        "inputs": ["avg_finish_last5", "win_rate_last5", "form_trend"],
        "status": "DEFINED_NOT_TRAINED",
    },
    {
        "id": "D",
        "name": "Contextual ranking",
        "description": (
            "Combine track + distance + breed + class (when present) contextual rates "
            "with sample_n reliability gates."
        ),
        "inputs": [
            "track_*",
            "distance_*",
            "breed_*",
            "class_*",
            "*_sample_n",
        ],
        "status": "DEFINED_NOT_TRAINED",
    },
]


def baseline_manifest() -> dict[str, Any]:
    return {
        "note": "Baselines are prepared for later comparison. DO NOT train ML in this phase.",
        "rule": "If future ML does not outperform A–D, do not deploy ML.",
        "baselines": BASELINES,
    }
