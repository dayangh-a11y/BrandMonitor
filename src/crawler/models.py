"""Crawler job queue models — resume / retry / duplicate prevention."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class CrawlJob(Base):
    __tablename__ = "crawl_jobs"
    __table_args__ = (
        UniqueConstraint("job_type", "dedupe_key", name="uq_crawl_job_dedupe"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(64), index=True)  # race|horse|race_list
    url: Mapped[str] = mapped_column(Text)
    dedupe_key: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", index=True
    )  # pending|running|success|failed|skipped_duplicate
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
