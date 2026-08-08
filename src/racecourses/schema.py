"""Ensure / seed ``ref_track_configurations`` without touching race history."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.base import Base
from src.racecourses.models import RefTrackConfiguration
from src.racecourses.track_config import TRACK_CONFIGURATIONS, propose_straight_length_update


def ensure_track_config_schema(session: Session) -> None:
    """Create the reference table if missing (SQLite-safe)."""
    import src.racecourses.models  # noqa: F401

    bind = session.get_bind()
    table = Base.metadata.tables.get("ref_track_configurations")
    if table is not None:
        Base.metadata.create_all(bind=bind, tables=[table])


def seed_track_configurations(session: Session) -> dict[str, Any]:
    """Insert missing rows; report conflicts; never overwrite confirmed values."""
    ensure_track_config_schema(session)
    inserted = 0
    unchanged = 0
    conflicts: list[dict[str, Any]] = []

    for cfg in TRACK_CONFIGURATIONS:
        existing = session.scalar(
            select(RefTrackConfiguration).where(RefTrackConfiguration.track_id == cfg.track_id)
        )
        if existing is None:
            session.add(
                RefTrackConfiguration(
                    track_id=cfg.track_id,
                    track_name=cfg.track_name,
                    city=cfg.city,
                    straight_length_m=cfg.straight_length_m,
                    straight_length_category=cfg.straight_length_category,
                    source=cfg.source,
                    source_url=cfg.source_url,
                    source_confidence=cfg.source_confidence,
                    source_note=cfg.source_note,
                )
            )
            inserted += 1
            continue
        if existing.straight_length_m != cfg.straight_length_m:
            report = propose_straight_length_update(
                cfg.track_id,
                cfg.straight_length_m,
                source=cfg.source,
                source_url=cfg.source_url,
                source_confidence=cfg.source_confidence,
            )
            conflicts.append(
                {
                    **report,
                    "db_straight_length_m": existing.straight_length_m,
                    "seed_straight_length_m": cfg.straight_length_m,
                }
            )
            # Keep DB value; optionally refresh metadata that does not change meters
        else:
            # Keep length; refresh display metadata if needed (name/city/category/source labels)
            existing.track_name = cfg.track_name
            existing.city = cfg.city
            existing.straight_length_category = cfg.straight_length_category
            existing.source = cfg.source
            existing.source_url = cfg.source_url
            existing.source_confidence = cfg.source_confidence
            existing.source_note = cfg.source_note
            unchanged += 1

    session.flush()
    return {
        "inserted": inserted,
        "unchanged_or_refreshed_meta": unchanged,
        "conflicts": conflicts,
        "total_configured": len(TRACK_CONFIGURATIONS),
    }


def list_track_configurations(session: Session) -> list[RefTrackConfiguration]:
    ensure_track_config_schema(session)
    return list(
        session.scalars(
            select(RefTrackConfiguration).order_by(RefTrackConfiguration.straight_length_m.desc())
        ).all()
    )
