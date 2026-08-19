"""ORM for independent Track Configuration reference table.

Append-stable reference data. Never overwrite historical race/result rows.
Conflicting proposed updates must be reported, not silently applied.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class RefTrackConfiguration(Base):
    """Independent reference: finishing straight length per track.

    Columns match the product contract:
    track_id, track_name, city, straight_length_m, source, source_url, source_confidence
    """

    __tablename__ = "ref_track_configurations"
    __table_args__ = (UniqueConstraint("track_id", name="uq_ref_track_configurations_track_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    track_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    track_name: Mapped[str] = mapped_column(String(128), nullable=False)
    city: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    straight_length_m: Mapped[int] = mapped_column(Integer, nullable=False)
    # Derived category persisted for query convenience (Short/Medium/Long)
    straight_length_category: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
