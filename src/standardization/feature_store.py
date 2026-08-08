"""Module 14 — Feature Store.

Store every derived feature once; reuse everywhere.
Never recalculate unnecessarily.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.analytics.models import AnlHorseMetrics
from src.standardization.constants import PLATFORM_VERSION
from src.standardization.models import StdFeatureStore

# Metrics projected into the feature store (layer=metrics → features)
HORSE_FEATURE_FIELDS = (
    "starts",
    "wins",
    "seconds",
    "thirds",
    "win_rate",
    "place_rate",
    "avg_finish",
    "performance_rating",
    "consistency_score",
    "form_score_3",
    "form_score_5",
    "form_score_10",
    "speed_index",
    "earnings_index",
    "earnings_total",
    "difficulty_index",
)

# Race-level Track Configuration features (apply only on confident track_id match)
RACE_TRACK_CONFIG_FEATURE_FIELDS = (
    "straight_length_m",
    "straight_length_category",
)


def get_feature(
    session: Session,
    *,
    entity_type: str,
    entity_id: int,
    feature_name: str,
    scope: str = "career",
    season_id: str = "*",
) -> StdFeatureStore | None:
    return session.scalar(
        select(StdFeatureStore).where(
            StdFeatureStore.entity_type == entity_type,
            StdFeatureStore.entity_id == entity_id,
            StdFeatureStore.feature_name == feature_name,
            StdFeatureStore.scope == scope,
            StdFeatureStore.season_id == season_id,
        )
    )


def upsert_feature(
    session: Session,
    *,
    entity_type: str,
    entity_id: int,
    feature_name: str,
    feature_value: float | None,
    scope: str = "career",
    season_id: str = "*",
    layer: str = "features",
    version: str = PLATFORM_VERSION,
    feature_json: dict[str, Any] | None = None,
    force: bool = False,
) -> StdFeatureStore:
    existing = get_feature(
        session,
        entity_type=entity_type,
        entity_id=entity_id,
        feature_name=feature_name,
        scope=scope,
        season_id=season_id,
    )
    if existing and not force and existing.version == version:
        # Reuse — do not recalculate
        return existing
    if existing:
        existing.feature_value = feature_value
        existing.feature_json = feature_json
        existing.layer = layer
        existing.version = version
        existing.computed_at = datetime.now(timezone.utc)
        return existing
    row = StdFeatureStore(
        entity_type=entity_type,
        entity_id=entity_id,
        feature_name=feature_name,
        feature_value=feature_value,
        feature_json=feature_json,
        scope=scope,
        season_id=season_id,
        layer=layer,
        version=version,
    )
    session.add(row)
    session.flush()
    return row


def materialize_horse_features(
    session: Session,
    *,
    scope: str | None = None,
    force: bool = False,
) -> dict[str, int]:
    """Project anl_horse_metrics into std_feature_store once per version."""
    q = select(AnlHorseMetrics).where(AnlHorseMetrics.breed == "*")
    if scope:
        q = q.where(AnlHorseMetrics.scope == scope)
    rows = list(session.scalars(q).all())
    if not rows:
        q2 = select(AnlHorseMetrics)
        if scope:
            q2 = q2.where(AnlHorseMetrics.scope == scope)
        by_key: dict[tuple[int, str, str], AnlHorseMetrics] = {}
        for r in session.scalars(q2).all():
            key = (r.horse_id, r.scope, r.season_key or "*")
            prev = by_key.get(key)
            if prev is None or (r.starts or 0) > (prev.starts or 0):
                by_key[key] = r
        rows = list(by_key.values())
    written = 0
    reused = 0
    for r in rows:
        season_id = r.season_key or "*"
        for field in HORSE_FEATURE_FIELDS:
            val = getattr(r, field, None)
            fv = float(val) if isinstance(val, (int, float)) else None
            before = get_feature(
                session,
                entity_type="horse",
                entity_id=r.horse_id,
                feature_name=field,
                scope=r.scope,
                season_id=season_id,
            )
            row = upsert_feature(
                session,
                entity_type="horse",
                entity_id=r.horse_id,
                feature_name=field,
                feature_value=fv,
                scope=r.scope,
                season_id=season_id,
                layer="metrics" if field in {"starts", "wins", "seconds", "thirds"} else "features",
                force=force,
            )
            if before and before.id == row.id and not force:
                reused += 1
            else:
                written += 1
    session.flush()
    logger.info("Feature store materialize written={} reused={}", written, reused)
    return {"written": written, "reused": reused, "source_rows": len(rows)}
