"""ORM persistence for pre-race intelligence reports."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class AnlPreraceReport(Base):
    """Complete pre-race intelligence report for one race card."""

    __tablename__ = "anl_prerace_reports"
    __table_args__ = (UniqueConstraint("race_id", name="uq_anl_prerace_race"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_id: Mapped[int] = mapped_column(
        ForeignKey("wh_races.id", ondelete="CASCADE"), index=True
    )
    race_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    racecourse_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    race_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    race_context_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    horses_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    reports_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    validation_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    publishable: Mapped[int] = mapped_column(Integer, default=1)  # 1/0 for sqlite portability
    report_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
