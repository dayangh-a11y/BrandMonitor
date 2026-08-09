"""Optional persistence for virtual race reports (no wh_races FK)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class AnlVirtualRaceReport(Base):
    """Saved virtual-race intelligence report (only when persist requested)."""

    __tablename__ = "anl_virtual_race_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    race_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    racecourse_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    race_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    distance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    race_class: Mapped[str | None] = mapped_column(String(64), nullable=True)

    scenario_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    race_context_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    horses_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    reports_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    pairwise_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    validation_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    resolution_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    report_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    publishable: Mapped[int] = mapped_column(Integer, default=1)
    version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
