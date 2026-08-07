"""Persistence for permanent horse identity + merge candidates."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class IdHorse(Base):
    """
    Permanent horse identity.

    All analytics / markets / prerace lookups should prefer this horse_id
    over display names.
    """

    __tablename__ = "id_horses"

    horse_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    sex: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sire_normalized: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    dam_normalized: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    meta_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="active", index=True
    )  # active|merged|retired
    merged_into_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("id_horses.horse_id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IdHorseLink(Base):
    """Map warehouse horse rows → permanent horse_id (many:1)."""

    __tablename__ = "id_horse_links"
    __table_args__ = (
        UniqueConstraint("warehouse_horse_id", name="uq_id_horse_link_wh"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    horse_id: Mapped[int] = mapped_column(
        ForeignKey("id_horses.horse_id", ondelete="CASCADE"), index=True
    )
    warehouse_horse_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    source_horse_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    method: Mapped[str] = mapped_column(String(64), default="build")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IdHorseAlias(Base):
    """Normalized name aliases pointing at permanent horse_id."""

    __tablename__ = "id_horse_aliases"
    __table_args__ = (
        UniqueConstraint("normalized_alias", "horse_id", name="uq_id_horse_alias"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    horse_id: Mapped[int] = mapped_column(
        ForeignKey("id_horses.horse_id", ondelete="CASCADE"), index=True
    )
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(64), default="observed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IdHorseMergeCandidate(Base):
    """Duplicate / possible-merge report rows."""

    __tablename__ = "id_horse_merge_candidates"
    __table_args__ = (
        UniqueConstraint(
            "left_horse_id",
            "right_horse_id",
            name="uq_id_horse_merge_pair",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    left_horse_id: Mapped[int] = mapped_column(
        ForeignKey("id_horses.horse_id", ondelete="CASCADE"), index=True
    )
    right_horse_id: Mapped[int] = mapped_column(
        ForeignKey("id_horses.horse_id", ondelete="CASCADE"), index=True
    )
    left_warehouse_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    right_warehouse_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    decision: Mapped[str] = mapped_column(String(32), default="candidate", index=True)
    evidence_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="open", index=True
    )  # open|merged|rejected
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IdHorseBuildRun(Base):
    """Audit row for identity resolution builds."""

    __tablename__ = "id_horse_build_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    profiles_loaded: Mapped[int] = mapped_column(Integer, default=0)
    permanent_ids: Mapped[int] = mapped_column(Integer, default=0)
    auto_merges: Mapped[int] = mapped_column(Integer, default=0)
    candidates: Mapped[int] = mapped_column(Integer, default=0)
    params_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
