"""
RAW layer — source-of-truth facts only.

Rules:
- Store only data collected from datasources (or faithful copies of it).
- Never store engineered / aggregated / pipeline-derived features here.
- Keep full JSON payloads for lineage and reprocessing.
- Features live exclusively under `src.database.features` and are built by pipelines.
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
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base


class RawIngestRun(Base):
    """One collector / ingest job execution."""

    __tablename__ = "raw_ingest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    input_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    races: Mapped[list["RawRace"]] = relationship(back_populates="ingest_run")


class RawHorse(Base):
    """Horse dimension as observed from source profiles / race cards."""

    __tablename__ = "raw_horses"
    __table_args__ = (
        UniqueConstraint("source", "source_horse_id", name="uq_raw_horses_source_id"),
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
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    race_entries: Mapped[list[RawRaceEntry]] = relationship(back_populates="horse")
    starts: Mapped[list[RawHorseStart]] = relationship(back_populates="horse")


class RawRace(Base):
    """Race card / result facts collected from a datasource."""

    __tablename__ = "raw_races"
    __table_args__ = (
        UniqueConstraint("source", "source_race_id", name="uq_raw_races_source_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ingest_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_ingest_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(64), index=True)
    source_race_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    race_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    track: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    province: Mapped[str | None] = mapped_column(String(128), nullable=True)
    distance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    surface: Mapped[str | None] = mapped_column(String(64), nullable=True)
    race_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weather: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prize_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    ingest_run: Mapped[RawIngestRun | None] = relationship(back_populates="races")
    entries: Mapped[list[RawRaceEntry]] = relationship(
        back_populates="race",
        cascade="all, delete-orphan",
    )


class RawRaceEntry(Base):
    """
    One horse's collected row on a race card / result.

    Contains only source-observed fields (weights, connections, official result).
    Derived stats (win rate, form, etc.) must NOT be added here.
    """

    __tablename__ = "raw_race_entries"
    __table_args__ = (
        UniqueConstraint("race_id", "source_horse_id", "number", name="uq_raw_race_entry"),
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
    # Source-published rating / handicap mark (not a pipeline feature)
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


class RawHorseStart(Base):
    """
    Historical start row collected from a horse profile page.

    Flat fact table for career history; no aggregated features.
    """

    __tablename__ = "raw_horse_starts"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "source_horse_id",
            "race_date",
            "race_number",
            "track",
            "number",
            name="uq_raw_horse_start",
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
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    horse: Mapped[RawHorse | None] = relationship(back_populates="starts")
