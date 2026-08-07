"""
RAW layer — append-only source extracts.

Rules:
- Store exactly what was extracted (type conversion only).
- No calculated / derived / cleaned analytics fields.
- Never overwrite prior Raw rows; append a new version when source_hash changes.
- Features must NEVER live here.
"""

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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base
from src.versioning.mixin import VersioningMixin


class RawIngestRun(Base):
    """One collector / ingest job execution."""

    __tablename__ = "raw_ingest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    input_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    parser_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    races: Mapped[list["RawRace"]] = relationship(back_populates="ingest_run")


class RawHorse(Base, VersioningMixin):
    """Horse extract versions (append-only)."""

    __tablename__ = "raw_horses"
    __table_args__ = (
        UniqueConstraint(
            "source", "source_horse_id", "version", name="uq_raw_horses_source_version"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    source_horse_id: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255))
    sex: Mapped[str | None] = mapped_column(String(32), nullable=True)
    birthdate: Mapped[date | None] = mapped_column(Date, nullable=True)
    profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    sire: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dam: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Exact extracted payload — no feature fields
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    race_entries: Mapped[list["RawRaceEntry"]] = relationship(back_populates="horse")
    starts: Mapped[list["RawHorseStart"]] = relationship(back_populates="horse")


class RawRace(Base, VersioningMixin):
    """Race extract versions (append-only)."""

    __tablename__ = "raw_races"
    __table_args__ = (
        UniqueConstraint(
            "source", "source_race_id", "version", name="uq_raw_races_source_version"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ingest_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_ingest_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(64), index=True)
    source_race_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    race_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    track: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    racecourse_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    province: Mapped[str | None] = mapped_column(String(128), nullable=True)
    distance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    surface: Mapped[str | None] = mapped_column(String(64), nullable=True)
    race_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weather: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prize_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    ingest_run: Mapped[RawIngestRun | None] = relationship(back_populates="races")
    entries: Mapped[list["RawRaceEntry"]] = relationship(
        back_populates="race",
        cascade="all, delete-orphan",
    )


class RawRaceEntry(Base, VersioningMixin):
    """One extracted race-card / result row (append-only per race version)."""

    __tablename__ = "raw_race_entries"
    __table_args__ = (
        UniqueConstraint(
            "race_id",
            "source_horse_id",
            "number",
            "version",
            name="uq_raw_race_entry_version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_id: Mapped[int] = mapped_column(
        ForeignKey("raw_races.id", ondelete="CASCADE"), index=True
    )
    horse_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_horses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_horse_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sex: Mapped[str | None] = mapped_column(String(32), nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    jockey: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    trainer: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    barrier: Mapped[int | None] = mapped_column(Integer, nullable=True)
    finish_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    race: Mapped[RawRace] = relationship(back_populates="entries")
    horse: Mapped[RawHorse | None] = relationship(back_populates="race_entries")


class RawHorseStart(Base, VersioningMixin):
    """Historical start row extracted from a horse profile (append-only)."""

    __tablename__ = "raw_horse_starts"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "source_horse_id",
            "race_date",
            "race_number",
            "track",
            "number",
            "version",
            name="uq_raw_horse_start_version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    horse_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_horses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_horse_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    race_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    race_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    track: Mapped[str | None] = mapped_column(String(128), nullable=True)
    race_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    surface: Mapped[str | None] = mapped_column(String(64), nullable=True)
    number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    jockey: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trainer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    barrier: Mapped[int | None] = mapped_column(Integer, nullable=True)
    finish_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    race_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    horse: Mapped[RawHorse | None] = relationship(back_populates="starts")


class RawParserError(Base):
    """Unexpected parser / extract anomalies captured during ingest."""

    __tablename__ = "raw_parser_errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_type: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
