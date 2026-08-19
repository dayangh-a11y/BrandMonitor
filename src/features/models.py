"""
FEATURE layer — empty shells for recalculable analytics features.

Rules:
- Features must NEVER be stored in Raw tables.
- Tables may be truncated and rebuilt at any time.
- This sprint ships infrastructure only (no statistics / ML fills).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class FeatHorseFeatures(Base):
    """HorseFeatures — empty feature row keyed by warehouse horse."""

    __tablename__ = "feat_horse_features"

    horse_id: Mapped[int] = mapped_column(
        ForeignKey("wh_horses.id", ondelete="CASCADE"), primary_key=True
    )
    features_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    feature_version: Mapped[str] = mapped_column(String(32), default="0")
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pipeline_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class FeatRaceFeatures(Base):
    """RaceFeatures — empty feature row keyed by warehouse race."""

    __tablename__ = "feat_race_features"

    race_id: Mapped[int] = mapped_column(
        ForeignKey("wh_races.id", ondelete="CASCADE"), primary_key=True
    )
    features_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    feature_version: Mapped[str] = mapped_column(String(32), default="0")
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pipeline_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class FeatTrainerFeatures(Base):
    """TrainerFeatures — empty feature row keyed by warehouse trainer."""

    __tablename__ = "feat_trainer_features"

    trainer_id: Mapped[int] = mapped_column(
        ForeignKey("wh_trainers.id", ondelete="CASCADE"), primary_key=True
    )
    features_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    feature_version: Mapped[str] = mapped_column(String(32), default="0")
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pipeline_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class FeatJockeyFeatures(Base):
    """JockeyFeatures — empty feature row keyed by warehouse jockey."""

    __tablename__ = "feat_jockey_features"

    jockey_id: Mapped[int] = mapped_column(
        ForeignKey("wh_jockeys.id", ondelete="CASCADE"), primary_key=True
    )
    features_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    feature_version: Mapped[str] = mapped_column(String(32), default="0")
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pipeline_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class FeatRecalcRun(Base):
    """Audit of feature recalculation jobs (infrastructure)."""

    __tablename__ = "feat_recalc_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rows_touched: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(String(1024), nullable=True)
