"""
FEATURES layer — derived metrics only.

Rules:
- No feature columns on Raw tables.
- Every feature row must be attributable to a pipeline run.
- Features are rebuildable: delete + recompute from Raw is always valid.
- Do not mix source payloads into feature tables.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class FeaturePipelineRun(Base):
    """Audit row for one feature-pipeline execution."""

    __tablename__ = "feat_pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_name: Mapped[str] = mapped_column(String(128), index=True)
    pipeline_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="running")
    params_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    rows_upserted: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class FeatHorseCareer(Base):
    """Career aggregates per horse — computed only by pipeline."""

    __tablename__ = "feat_horse_career"

    horse_id: Mapped[int] = mapped_column(
        ForeignKey("raw_horses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    pipeline_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("feat_pipeline_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    starts: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    places: Mapped[int] = mapped_column(Integer, default=0)  # finish in 1..3
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    place_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_finish: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_race_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    days_since_last_race: Mapped[int | None] = mapped_column(Integer, nullable=True)


class FeatHorseForm(Base):
    """Rolling recent-form features per horse / window."""

    __tablename__ = "feat_horse_form"
    __table_args__ = (
        UniqueConstraint("horse_id", "window_size", name="uq_feat_horse_form_window"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    horse_id: Mapped[int] = mapped_column(
        ForeignKey("raw_horses.id", ondelete="CASCADE"), index=True
    )
    window_size: Mapped[int] = mapped_column(Integer, default=5)
    pipeline_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("feat_pipeline_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    recent_starts: Mapped[int] = mapped_column(Integer, default=0)
    recent_wins: Mapped[int] = mapped_column(Integer, default=0)
    recent_avg_finish: Mapped[float | None] = mapped_column(Float, nullable=True)
    form_string: Mapped[str | None] = mapped_column(String(64), nullable=True)


class FeatHorseDistance(Base):
    """Performance buckets by race distance — pipeline-only."""

    __tablename__ = "feat_horse_distance"
    __table_args__ = (
        UniqueConstraint("horse_id", "distance", name="uq_feat_horse_distance"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    horse_id: Mapped[int] = mapped_column(
        ForeignKey("raw_horses.id", ondelete="CASCADE"), index=True
    )
    distance: Mapped[int] = mapped_column(Integer)
    pipeline_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("feat_pipeline_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    starts: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    avg_finish: Mapped[float | None] = mapped_column(Float, nullable=True)


class FeatJockeyStats(Base):
    """Jockey aggregates derived from raw starts / entries."""

    __tablename__ = "feat_jockey_stats"

    jockey: Mapped[str] = mapped_column(String(255), primary_key=True)
    pipeline_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("feat_pipeline_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    starts: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)


class FeatTrainerStats(Base):
    """Trainer aggregates derived from raw starts / entries."""

    __tablename__ = "feat_trainer_stats"

    trainer: Mapped[str] = mapped_column(String(255), primary_key=True)
    pipeline_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("feat_pipeline_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    starts: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
