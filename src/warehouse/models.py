"""
WAREHOUSE layer — normalized, curated entities for analytics platforms.

Built from current Raw versions via ETL. Not a dump of website HTML.
Does not store ML features.
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


class WhHorse(Base):
    __tablename__ = "wh_horses"
    __table_args__ = (UniqueConstraint("source", "source_horse_id", name="uq_wh_horses"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    source_horse_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    sex: Mapped[str | None] = mapped_column(String(32), nullable=True)
    birthdate: Mapped[date | None] = mapped_column(Date, nullable=True)
    profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    raw_horse_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    results: Mapped[list["WhRaceResult"]] = relationship(back_populates="horse")


class WhRace(Base):
    __tablename__ = "wh_races"
    __table_args__ = (UniqueConstraint("source", "source_race_id", name="uq_wh_races"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
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
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_race_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    results: Mapped[list["WhRaceResult"]] = relationship(back_populates="race")
    videos: Mapped[list["WhRaceVideo"]] = relationship(back_populates="race")


class WhJockey(Base):
    __tablename__ = "wh_jockeys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    canonical_entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WhTrainer(Base):
    __tablename__ = "wh_trainers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    canonical_entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WhOwner(Base):
    __tablename__ = "wh_owners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    canonical_entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WhRaceResult(Base):
    __tablename__ = "wh_race_results"
    __table_args__ = (
        UniqueConstraint("race_id", "horse_id", "number", name="uq_wh_race_result"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_id: Mapped[int] = mapped_column(ForeignKey("wh_races.id", ondelete="CASCADE"), index=True)
    horse_id: Mapped[int | None] = mapped_column(
        ForeignKey("wh_horses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    jockey_id: Mapped[int | None] = mapped_column(
        ForeignKey("wh_jockeys.id", ondelete="SET NULL"), nullable=True, index=True
    )
    trainer_id: Mapped[int | None] = mapped_column(
        ForeignKey("wh_trainers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("wh_owners.id", ondelete="SET NULL"), nullable=True, index=True
    )
    number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    barrier: Mapped[int | None] = mapped_column(Integer, nullable=True)
    finish_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    odds: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_entry_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    race: Mapped[WhRace] = relationship(back_populates="results")
    horse: Mapped[WhHorse | None] = relationship(back_populates="results")


class WhRaceVideo(Base):
    """Race media links extracted from source payloads (no video analysis)."""

    __tablename__ = "wh_race_videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_id: Mapped[int] = mapped_column(ForeignKey("wh_races.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    race: Mapped[WhRace] = relationship(back_populates="videos")


class WhHorsePedigree(Base):
    """Pedigree placeholder — structure only; no pedigree analysis."""

    __tablename__ = "wh_horse_pedigree"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    horse_id: Mapped[int] = mapped_column(
        ForeignKey("wh_horses.id", ondelete="CASCADE"), unique=True, index=True
    )
    sire_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dam_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sire_horse_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dam_horse_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WhEntityMatch(Base):
    """Entity-resolution candidate / confirmed match between aliases."""

    __tablename__ = "wh_entity_matches"
    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "left_key",
            "right_key",
            name="uq_wh_entity_match",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)  # horse|jockey|trainer|owner
    left_key: Mapped[str] = mapped_column(String(255), index=True)
    right_key: Mapped[str] = mapped_column(String(255), index=True)
    score: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(64), default="fuzzy")
    status: Mapped[str] = mapped_column(String(32), default="candidate")  # candidate|confirmed|rejected
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
