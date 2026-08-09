"""SQLAlchemy mixin for lineage / versioning columns on Raw rows."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column


class VersioningMixin:
    """
    Required on every imported Raw record.

    History policy: never UPDATE payload fields in place.
    Insert a new row, mark previous is_current=False.
    """

    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    parser_version: Mapped[str] = mapped_column(String(32), default="2.0.0")
    crawl_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    source_hash: Mapped[str] = mapped_column(String(64), index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
