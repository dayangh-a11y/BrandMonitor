"""Ensure sex-normalization schema columns/tables exist (SQLite-safe)."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from src.database.base import Base


def ensure_sex_schema(session: Session) -> None:
    """Create new tables and add missing columns on anl_horse_metrics."""
    import src.analytics.models  # noqa: F401 — register tables on Base.metadata

    bind = session.get_bind()
    tables = []
    for name in ("anl_sex_metrics", "anl_race_sex"):
        if name in Base.metadata.tables:
            tables.append(Base.metadata.tables[name])
    if tables:
        Base.metadata.create_all(bind=bind, tables=tables)
    insp = inspect(bind)
    if "anl_horse_metrics" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("anl_horse_metrics")}
    alters: list[str] = []
    if "sex_normalized" not in cols:
        alters.append(
            "ALTER TABLE anl_horse_metrics ADD COLUMN sex_normalized VARCHAR(32)"
        )
    if "sex_adjusted_performance_rating" not in cols:
        alters.append(
            "ALTER TABLE anl_horse_metrics "
            "ADD COLUMN sex_adjusted_performance_rating FLOAT"
        )
    for ddl in alters:
        session.execute(text(ddl))
    if alters:
        session.flush()
