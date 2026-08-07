"""ORM models for standardization tables (std_*)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class StdEntity(Base):
    """Permanent entity ID — never rely on display names (Module 2)."""

    __tablename__ = "std_entities"
    __table_args__ = (
        UniqueConstraint("entity_type", "normalized_key", name="uq_std_entity_norm"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    # horse|trainer|jockey|owner|sire|stable|track
    display_name: Mapped[str] = mapped_column(String(255), index=True)
    normalized_key: Mapped[str] = mapped_column(String(255), index=True)
    warehouse_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    meta_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class StdEntityAlias(Base):
    """Alternate spellings mapped to a permanent entity id."""

    __tablename__ = "std_entity_aliases"
    __table_args__ = (
        UniqueConstraint("entity_type", "normalized_alias", name="uq_std_alias"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    alias: Mapped[str] = mapped_column(String(255))
    normalized_alias: Mapped[str] = mapped_column(String(255), index=True)
    method: Mapped[str] = mapped_column(String(64), default="exact_normalized")


class StdSeason(Base):
    """Standardized season registry — no hardcoded season keys (Module 3)."""

    __tablename__ = "std_seasons"
    __table_args__ = (UniqueConstraint("season_id", name="uq_std_season_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_id: Mapped[str] = mapped_column(String(64), index=True)
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date, index=True)
    track: Mapped[str] = mapped_column(String(128), index=True)
    country: Mapped[str] = mapped_column(String(8), default="IR")
    year: Mapped[int] = mapped_column(Integer, index=True)
    racecourse_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_latest_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    race_days: Mapped[int] = mapped_column(Integer, default=0)
    heats: Mapped[int] = mapped_column(Integer, default=0)
    legacy_season_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    meta_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class StdRaceClassification(Base):
    """Every race classified (Module 4)."""

    __tablename__ = "std_race_classifications"
    __table_args__ = (UniqueConstraint("race_id", name="uq_std_race_class"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_id: Mapped[int] = mapped_column(Integer, index=True)  # wh_races.id
    distance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    surface: Mapped[str | None] = mapped_column(String(64), nullable=True)  # breed/bloodline
    going: Mapped[str | None] = mapped_column(String(64), nullable=True)  # track condition
    class_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    age_restriction: Mapped[str | None] = mapped_column(String(64), nullable=True)
    breed: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sex_restriction: Mapped[str | None] = mapped_column(String(64), nullable=True)
    track_condition: Mapped[str | None] = mapped_column(String(64), nullable=True)
    weather: Mapped[str | None] = mapped_column(String(128), nullable=True)
    race_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    difficulty: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_bucket: Mapped[str | None] = mapped_column(String(32), nullable=True)
    completeness: Mapped[float | None] = mapped_column(Float, nullable=True)
    missing_fields_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    meta_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class StdVersionRegistry(Base):
    """Version ledger for metrics, rules, weights, formulas, queries (Module 12)."""

    __tablename__ = "std_version_registry"
    __table_args__ = (
        UniqueConstraint("artifact_type", "artifact_name", "version", name="uq_std_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    artifact_type: Mapped[str] = mapped_column(String(64), index=True)
    # metric|rule|weight|formula|query|module|ranking
    artifact_name: Mapped[str] = mapped_column(String(128), index=True)
    version: Mapped[str] = mapped_column(String(32))
    definition_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class StdAuditLog(Base):
    """Immutable audit of questions / rules / SQL / rows (Module 13)."""

    __tablename__ = "std_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    sql_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    rows_analyzed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    execution_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(32), nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class StdFeatureStore(Base):
    """Derived features stored once, reused everywhere (Module 14)."""

    __tablename__ = "std_feature_store"
    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "entity_id",
            "feature_name",
            "scope",
            "season_id",
            name="uq_std_feature",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    feature_name: Mapped[str] = mapped_column(String(128), index=True)
    feature_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    feature_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    scope: Mapped[str] = mapped_column(String(32), default="career")
    season_id: Mapped[str] = mapped_column(String(64), default="*")
    layer: Mapped[str] = mapped_column(String(32), default="features")  # AI layer
    version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class StdDqReport(Base):
    """Persisted Data Quality Report summary (Module 1)."""

    __tablename__ = "std_dq_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(32), default="ok")
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    issues_count: Mapped[int] = mapped_column(Integer, default=0)
    report_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class StdBenchmark(Base):
    """Horse vs peer averages (Module 11)."""

    __tablename__ = "std_benchmarks"
    __table_args__ = (
        UniqueConstraint(
            "horse_id",
            "scope",
            "season_id",
            "metric_name",
            name="uq_std_benchmark",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    horse_id: Mapped[int] = mapped_column(Integer, index=True)
    scope: Mapped[str] = mapped_column(String(32), default="season")
    season_id: Mapped[str] = mapped_column(String(64), default="*")
    metric_name: Mapped[str] = mapped_column(String(64), index=True)
    horse_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    breed_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    season_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    career_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    track_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    delta_vs_season: Mapped[float | None] = mapped_column(Float, nullable=True)
    meta_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
