"""ORM mirrors for hierarchy tables (materialized by rebuild_race_hierarchy)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class WhRaceWeek(Base):
    """Race Week — official competition week/period (source week id)."""

    __tablename__ = "wh_race_weeks"

    race_week_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source: Mapped[str] = mapped_column(String(64), default="asbdavani")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    heat_count: Mapped[int] = mapped_column(Integer, default=0)
    race_day_count: Mapped[int] = mapped_column(Integer, default=0)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    unique_horse_count: Mapped[int] = mapped_column(Integer, default=0)
    first_race_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_race_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WhRaceDay(Base):
    """Race Day — one calendar day at one venue under a Race Week.

    Never equal to a Heat. ID = ``{date}|{racecourse_code}|{week_id}``.
    """

    __tablename__ = "wh_race_days"

    race_day_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    race_week_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("wh_race_weeks.race_week_id"), nullable=True, index=True
    )
    race_date: Mapped[date] = mapped_column(Date, index=True)
    race_date_jalali: Mapped[str | None] = mapped_column(String(32), nullable=True)
    jalali_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    track: Mapped[str] = mapped_column(String(128))
    racecourse_code: Mapped[str] = mapped_column(String(64), index=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    heat_count: Mapped[int] = mapped_column(Integer, default=0)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    unique_horse_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WhHeatHierarchy(Base):
    """Heat projection with upward links to Race Day and Race Week."""

    __tablename__ = "wh_heat_hierarchy"

    heat_id: Mapped[int] = mapped_column(Integer, primary_key=True)  # wh_races.id
    heat_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    race_day_id: Mapped[str | None] = mapped_column(
        String(255), ForeignKey("wh_race_days.race_day_id"), nullable=True, index=True
    )
    race_week_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("wh_race_weeks.race_week_id"), nullable=True, index=True
    )
    source_race_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    race_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    race_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    track: Mapped[str | None] = mapped_column(String(128), nullable=True)
    racecourse_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    unique_horse_count: Mapped[int] = mapped_column(Integer, default=0)
    link_complete: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
