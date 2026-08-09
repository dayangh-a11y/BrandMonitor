"""ORM models for market analytics persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
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


class AnlMarketRace(Base):
    """Per-race multi-market snapshot."""

    __tablename__ = "anl_market_races"
    __table_args__ = (UniqueConstraint("race_id", name="uq_anl_market_race"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_id: Mapped[int] = mapped_column(
        ForeignKey("wh_races.id", ondelete="CASCADE"), index=True
    )
    win_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    place_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    without_favorite_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    value_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    risk_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    surprise_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    h2h_pairs: Mapped[int] = mapped_column(Integer, default=0)
    meta_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AnlMarketPairwise(Base):
    """Stored pairwise comparison for a race (complete matrix rows)."""

    __tablename__ = "anl_market_pairwise"
    __table_args__ = (
        UniqueConstraint(
            "race_id",
            "horse_a_id",
            "horse_b_id",
            name="uq_anl_market_pair",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_id: Mapped[int] = mapped_column(
        ForeignKey("wh_races.id", ondelete="CASCADE"), index=True
    )
    horse_a_id: Mapped[int] = mapped_column(Integer, index=True)
    horse_a_name: Mapped[str] = mapped_column(String(255))
    horse_b_id: Mapped[int] = mapped_column(Integer, index=True)
    horse_b_name: Mapped[str] = mapped_column(String(255))
    a_ahead_prob: Mapped[float] = mapped_column(Float)
    b_ahead_prob: Mapped[float] = mapped_column(Float)
    expected_finish_gap: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class AnlMarketMatchup(Base):
    """Audited direct matchup answers (A vs B)."""

    __tablename__ = "anl_market_matchups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    horse_a_id: Mapped[int] = mapped_column(Integer, index=True)
    horse_a_name: Mapped[str] = mapped_column(String(255))
    horse_b_id: Mapped[int] = mapped_column(Integer, index=True)
    horse_b_name: Mapped[str] = mapped_column(String(255))
    query_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    p_a_ahead: Mapped[float] = mapped_column(Float)
    p_b_ahead: Mapped[float] = mapped_column(Float)
    confidence: Mapped[str | None] = mapped_column(String(32), nullable=True)
    answer_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
