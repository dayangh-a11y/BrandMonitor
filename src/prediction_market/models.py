"""ORM models for prediction-market Raw / Warehouse / Analytics tables."""

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


# ---------------------------------------------------------------------------
# RAW — append-only API snapshots
# ---------------------------------------------------------------------------


class RawPredictionSnapshot(Base):
    """Append-only JSON snapshot from mosharekat public API."""

    __tablename__ = "raw_prediction_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "snapshot_kind",
            "source_key",
            "captured_at",
            name="uq_raw_pred_snap",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), index=True, default="mosharekat")
    snapshot_kind: Mapped[str] = mapped_column(String(64), index=True)
    source_key: Mapped[str] = mapped_column(String(128), index=True)
    endpoint: Mapped[str | None] = mapped_column(Text, nullable=True)
    race_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    is_pre_race: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


# ---------------------------------------------------------------------------
# WAREHOUSE — normalized prediction market entities
# ---------------------------------------------------------------------------


class WhPredictionEvent(Base):
    """One prediction-market race event (mosharekat race)."""

    __tablename__ = "wh_prediction_events"
    __table_args__ = (
        UniqueConstraint("source", "source_event_id", name="uq_wh_pred_event"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), index=True, default="mosharekat")
    source_event_id: Mapped[str] = mapped_column(String(64), index=True)
    source_day_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    day_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    race_number: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    race_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    track_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    track_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    field_size: Mapped[int] = mapped_column(Integer, default=0)
    wh_race_id: Mapped[int | None] = mapped_column(
        ForeignKey("wh_races.id", ondelete="SET NULL"), nullable=True, index=True
    )
    meta_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WhPredictionEntry(Base):
    """
    Per-horse market / survey entry for an event.

    Public API does not expose per-user bets without auth; each row is the
    aggregated market signal for one runner (odds + survey counts).
    """

    __tablename__ = "wh_prediction_entries"
    __table_args__ = (
        UniqueConstraint(
            "event_id", "cloth_number", "market_type", name="uq_wh_pred_entry"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("wh_prediction_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cloth_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    horse_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_horse_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    jockey_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scratched: Mapped[bool] = mapped_column(Boolean, default=False)
    actual_rank: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    market_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Discovered market fields stored generically
    odd: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    overflow_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    survey_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    implied_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    crowd_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wh_horse_id: Mapped[int | None] = mapped_column(
        ForeignKey("wh_horses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    snapshot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_pre_race_snapshot: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class WhPredictionStatistic(Base):
    """Aggregated prediction statistics for an event (distribution summary)."""

    __tablename__ = "wh_prediction_statistics"
    __table_args__ = (
        UniqueConstraint("event_id", "stat_type", name="uq_wh_pred_stat"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("wh_prediction_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stat_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    total_participants: Mapped[int | None] = mapped_column(Integer, nullable=True)
    favorite_cloth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    favorite_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    favorite_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    entropy: Mapped[float | None] = mapped_column(Float, nullable=True)
    variance: Mapped[float | None] = mapped_column(Float, nullable=True)
    distribution_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    snapshot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_pre_race_snapshot: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class WhPredictionReward(Base):
    """Pool / prize pool row discovered on a race day."""

    __tablename__ = "wh_prediction_rewards"
    __table_args__ = (
        UniqueConstraint("source", "source_pool_id", name="uq_wh_pred_reward"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), default="mosharekat")
    source_pool_id: Mapped[str] = mapped_column(String(64), index=True)
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("wh_prediction_events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_day_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    pool_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    prize_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ticket_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_prize: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    share: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_race_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_race_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WhPredictionWinner(Base):
    """Winning selection / horse for a pool or race result."""

    __tablename__ = "wh_prediction_winners"
    __table_args__ = (
        UniqueConstraint(
            "event_id", "pool_type", "cloth_number", "place", name="uq_wh_pred_winner"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("wh_prediction_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reward_id: Mapped[int | None] = mapped_column(
        ForeignKey("wh_prediction_rewards.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    pool_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    cloth_number: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    horse_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    place: Mapped[int | None] = mapped_column(Integer, nullable=True)
    odd_asli: Mapped[float | None] = mapped_column(Float, nullable=True)
    odd_pardakhti: Mapped[float | None] = mapped_column(Float, nullable=True)
    prize_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    wh_horse_id: Mapped[int | None] = mapped_column(
        ForeignKey("wh_horses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


# ---------------------------------------------------------------------------
# ANALYTICS
# ---------------------------------------------------------------------------


class AnlPredictionRaceMetrics(Base):
    __tablename__ = "anl_prediction_race_metrics"
    __table_args__ = (UniqueConstraint("event_id", name="uq_anl_pred_race"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    race_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    track_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    field_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    crowd_favorite_cloth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    crowd_favorite_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    crowd_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    crowd_win_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    prediction_distribution_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    surprise_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    upset_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    favorite_failure_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    prediction_difficulty: Mapped[float | None] = mapped_column(Float, nullable=True)
    crowd_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    crowd_bias: Mapped[float | None] = mapped_column(Float, nullable=True)
    shock_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    difficulty_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    prediction_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    participants: Mapped[int | None] = mapped_column(Integer, nullable=True)
    winners_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_prize_pool: Mapped[float | None] = mapped_column(Float, nullable=True)
    average_prize: Mapped[float | None] = mapped_column(Float, nullable=True)
    winning_prediction_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ML feature pack
    crowd_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    prediction_gap: Mapped[float | None] = mapped_column(Float, nullable=True)
    public_bias: Mapped[float | None] = mapped_column(Float, nullable=True)
    favorite_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    favorite_failed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prediction_entropy: Mapped[float | None] = mapped_column(Float, nullable=True)
    prediction_variance: Mapped[float | None] = mapped_column(Float, nullable=True)
    features_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    explain_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AnlPredictionEntityMetrics(Base):
    """Horse / trainer / jockey / owner / sire prediction-market metrics."""

    __tablename__ = "anl_prediction_entity_metrics"
    __table_args__ = (
        UniqueConstraint(
            "entity_type", "entity_key", "scope", "season_key", name="uq_anl_pred_entity"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)  # horse|trainer|jockey|owner|sire
    entity_key: Mapped[str] = mapped_column(String(255), index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    entity_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(32), default="career", index=True)
    season_key: Mapped[str] = mapped_column(String(64), default="*", index=True)
    starts: Mapped[int] = mapped_column(Integer, default=0)

    public_popularity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    public_trust_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    overrated_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    underrated_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    unpredictability_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    surprise_frequency: Mapped[float | None] = mapped_column(Float, nullable=True)
    favorite_failure_frequency: Mapped[float | None] = mapped_column(Float, nullable=True)
    upset_victory_frequency: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_prediction_rank: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_actual_rank: Mapped[float | None] = mapped_column(Float, nullable=True)
    prediction_gap: Mapped[float | None] = mapped_column(Float, nullable=True)
    metrics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AnlPredictionBuildRun(Base):
    __tablename__ = "anl_prediction_build_runs"

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
