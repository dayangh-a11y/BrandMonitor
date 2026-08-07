"""Analytics ORM models (anl_*)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class AnlBuildRun(Base):
    """Audit row for one analytics rebuild."""

    __tablename__ = "anl_build_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    builder_version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    params_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    rows_written: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class AnlSeason(Base):
    """Inferred racing season / meeting cluster per racecourse."""

    __tablename__ = "anl_seasons"
    __table_args__ = (
        UniqueConstraint("season_key", name="uq_anl_season_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_key: Mapped[str] = mapped_column(String(128), index=True)
    racecourse_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date, index=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_latest_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    race_days: Mapped[int] = mapped_column(Integer, default=0)
    heats: Mapped[int] = mapped_column(Integer, default=0)
    meta_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class AnlHorseMetrics(Base):
    """
    Standardized horse performance metrics for a scope (career or season).

    Designed as a flat, ML-joinable feature row plus explainability fields.
    """

    __tablename__ = "anl_horse_metrics"
    __table_args__ = (
        UniqueConstraint(
            "horse_id",
            "scope",
            "season_key",
            "breed",
            name="uq_anl_horse_metrics_scope",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    horse_id: Mapped[int] = mapped_column(
        ForeignKey("wh_horses.id", ondelete="CASCADE"), index=True
    )
    horse_name: Mapped[str] = mapped_column(String(255), index=True)
    scope: Mapped[str] = mapped_column(String(32), index=True)  # career|season
    season_key: Mapped[str] = mapped_column(String(128), default="*", index=True)
    breed: Mapped[str] = mapped_column(String(64), default="*", index=True)  # surface or *

    # Volume
    starts: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    seconds: Mapped[int] = mapped_column(Integer, default=0)
    thirds: Mapped[int] = mapped_column(Integer, default=0)
    places: Mapped[int] = mapped_column(Integer, default=0)

    # Core rates
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    place_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_finish: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Standardized indices (typically 0..100 unless noted)
    performance_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    consistency_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    form_score_3: Mapped[float | None] = mapped_column(Float, nullable=True)
    form_score_5: Mapped[float | None] = mapped_column(Float, nullable=True)
    form_score_10: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    earnings_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    earnings_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    difficulty_index: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Preferences (best bucket key + strength 0..1)
    track_preference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    track_preference_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_preference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    distance_preference_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    weather_preference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    weather_preference_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    track_condition_preference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    track_condition_preference_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Combinations
    jockey_combination_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_jockey: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trainer_combination_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_trainer: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Form dynamics
    fatigue_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    improvement_trend: Mapped[float | None] = mapped_column(Float, nullable=True)
    decline_trend: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_improving: Mapped[bool] = mapped_column(Boolean, default=False)
    is_declining: Mapped[bool] = mapped_column(Boolean, default=False)

    # Demographics / class context
    age_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    age_band: Mapped[str | None] = mapped_column(String(32), nullable=True)
    primary_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sire_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Rankings within scope
    season_ranking: Mapped[int | None] = mapped_column(Integer, nullable=True)
    career_ranking: Mapped[int | None] = mapped_column(Integer, nullable=True)
    breed_ranking: Mapped[int | None] = mapped_column(Integer, nullable=True)

    explain_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    explain_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    features_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    build_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("anl_build_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AnlRanking(Base):
    """
    Precomputed leaderboard rows with explainability.

    ``category`` examples:
      best_season, most_successful, most_consistent, improving, declining,
      best_young, best_by_breed, best_by_age, best_by_class,
      best_by_distance, best_by_track_condition, best_by_weather,
      best_trainer, best_jockey, best_owner, best_sire
    """

    __tablename__ = "anl_rankings"
    __table_args__ = (
        UniqueConstraint(
            "category",
            "scope",
            "season_key",
            "segment",
            "entity_type",
            "entity_key",
            name="uq_anl_ranking_row",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    scope: Mapped[str] = mapped_column(String(32), index=True)  # career|season
    season_key: Mapped[str] = mapped_column(String(128), default="*", index=True)
    segment: Mapped[str] = mapped_column(String(128), default="*", index=True)
    # segment holds breed / age_band / class / distance bucket / weather / track_condition

    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    # horse|trainer|jockey|owner|sire
    entity_key: Mapped[str] = mapped_column(String(255), index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    entity_name: Mapped[str] = mapped_column(String(255), index=True)

    rank: Mapped[int] = mapped_column(Integer, index=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    metric_primary: Mapped[str | None] = mapped_column(String(64), nullable=True)

    starts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wins: Mapped[int | None] = mapped_column(Integer, nullable=True)
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    place_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_finish: Mapped[float | None] = mapped_column(Float, nullable=True)
    performance_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    consistency_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    form_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    earnings_total: Mapped[float | None] = mapped_column(Float, nullable=True)

    why_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    why_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    build_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("anl_build_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
