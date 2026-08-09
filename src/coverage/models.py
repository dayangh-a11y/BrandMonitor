"""Coverage-first tables: missing gaps, source conflicts, priorities, pipeline runs."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    JSON,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class CovSourcePriority(Base):
    """Declared priority for resolving cross-source conflicts (lower rank = higher priority)."""

    __tablename__ = "cov_source_priorities"
    __table_args__ = (UniqueConstraint("source", name="uq_cov_source_priority"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    priority_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CovMissingGap(Base):
    """Marked Missing Coverage ranges — never assume emptiness means no racing."""

    __tablename__ = "cov_missing_gaps"
    __table_args__ = (
        UniqueConstraint(
            "scope_type",
            "jalali_year",
            "jalali_month",
            "track",
            "breed",
            name="uq_cov_missing_gap",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope_type: Mapped[str] = mapped_column(String(32), index=True)  # year|month|city_month|breed_month
    jalali_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    jalali_month: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    track: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    breed: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    gregorian_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    gregorian_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    # open | investigating | partially_filled | resolved | blocked
    evidence_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    suggested_sources_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CovSourceConflict(Base):
    """Two sources disagree — never auto-pick; store both + priority hint."""

    __tablename__ = "cov_source_conflicts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)  # race|result|horse
    entity_key: Mapped[str] = mapped_column(String(255), index=True)
    field_name: Mapped[str] = mapped_column(String(64), index=True)
    source_a: Mapped[str] = mapped_column(String(64))
    value_a_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    source_url_a: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_b: Mapped[str] = mapped_column(String(64))
    value_b_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    source_url_b: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    # open | resolved_by_priority | resolved_manual
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CovPipelineRun(Base):
    """One coverage ETL stage run with before/after metrics."""

    __tablename__ = "cov_pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stage: Mapped[str] = mapped_column(String(64), index=True)
    # extract|normalize|validate|deduplicate|match_identity|merge|integrity|full
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    metrics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    report_path: Mapped[str | None] = mapped_column(Text, nullable=True)


class CovEnrichmentGate(Base):
    """Hard gate: secondary enrichment blocked until coverage threshold met."""

    __tablename__ = "cov_enrichment_gates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    min_coverage_pct: Mapped[float] = mapped_column(Float, default=70.0)
    current_coverage_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
