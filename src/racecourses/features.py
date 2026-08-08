"""Race / horse feature fields contributed by Track Configuration.

These are lookup features (not inventable). Apply only when the race
confidently matches a configured ``track_id``.
"""

from __future__ import annotations

from typing import Any

from src.racecourses.track_config import (
    build_track_context,
    straight_length_features,
)

# Explicit Feature Set columns (product contract §14)
TRACK_CONFIG_FEATURE_FIELDS: tuple[str, ...] = (
    "straight_length_m",
    "straight_length_category",
)

# Full Track Context fields for Performance Score (§6)
TRACK_CONTEXT_FIELDS: tuple[str, ...] = (
    "race_distance",
    "straight_length_m",
    "track_id",  # Track/City identity
    "city",
    "breed",
    "horse_age",
    "weight",
    "starting_gate",
    "finish_position",
    "finish_time",
    "number_of_runners",
)


def merge_track_config_into_features(
    features: dict[str, Any] | None,
    *,
    racecourse_code: str | None = None,
    track_name: str | None = None,
    city: str | None = None,
) -> dict[str, Any]:
    """Merge straight-length features into a feature dict (no overwrite of other keys)."""
    out = dict(features or {})
    feats = straight_length_features(
        racecourse_code=racecourse_code,
        track_name=track_name,
        city=city,
    )
    for key in TRACK_CONFIG_FEATURE_FIELDS:
        out[key] = feats.get(key)
    out["track_config_applied"] = feats.get("track_config_applied", False)
    if feats.get("track_id"):
        out["track_id"] = feats["track_id"]
    return out


def track_context_from_race_result(
    *,
    racecourse_code: str | None,
    track_name: str | None,
    city: str | None = None,
    race_distance: int | None = None,
    breed: str | None = None,
    horse_age: int | float | None = None,
    weight: float | None = None,
    starting_gate: int | None = None,
    finish_position: int | None = None,
    finish_time: str | float | None = None,
    number_of_runners: int | None = None,
) -> dict[str, Any]:
    """Build Track Context dict for Performance Score / Finish Performance."""
    ctx = build_track_context(
        racecourse_code=racecourse_code,
        track_name=track_name,
        city=city,
        race_distance=race_distance,
        breed=breed,
        horse_age=horse_age,
        weight=weight,
        starting_gate=starting_gate,
        finish_position=finish_position,
        finish_time=finish_time,
        number_of_runners=number_of_runners,
    )
    return ctx.as_dict()
