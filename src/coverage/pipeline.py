"""Coverage-first ETL: Extract → Normalize → Validate → Deduplicate → Match → Merge → Integrity."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from loguru import logger
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from src.coverage.dates import dual_dates, jalali_string
from src.coverage.gaps import coverage_snapshot, detect_and_upsert_missing_gaps
from src.coverage.models import (
    CovEnrichmentGate,
    CovPipelineRun,
    CovSourceConflict,
    CovSourcePriority,
)
from src.coverage.policy import (
    BLOCKED_ENRICHMENT,
    DEFAULT_COVERAGE_GATE_PCT,
    DEFAULT_SOURCE_PRIORITIES,
    preferred_source,
)
from src.utils.jalali import format_jalali

ART = Path("/opt/cursor/artifacts")


def ensure_source_priorities(session: Session) -> int:
    n = 0
    for source, rank, notes in DEFAULT_SOURCE_PRIORITIES:
        row = session.scalar(select(CovSourcePriority).where(CovSourcePriority.source == source))
        if row is None:
            session.add(CovSourcePriority(source=source, priority_rank=rank, notes=notes))
            n += 1
        else:
            row.priority_rank = rank
            row.notes = notes
    session.flush()
    return n


def ensure_enrichment_gate(session: Session, coverage_pct: float | None = None) -> dict[str, Any]:
    gate = session.scalar(select(CovEnrichmentGate).where(CovEnrichmentGate.name == "secondary"))
    if gate is None:
        gate = CovEnrichmentGate(
            name="secondary",
            allowed=False,
            min_coverage_pct=DEFAULT_COVERAGE_GATE_PCT,
            notes="Blocks: " + ", ".join(BLOCKED_ENRICHMENT),
        )
        session.add(gate)
    if coverage_pct is not None:
        gate.current_coverage_pct = coverage_pct
        gate.allowed = coverage_pct >= gate.min_coverage_pct
    session.flush()
    return {
        "allowed": gate.allowed,
        "min_coverage_pct": gate.min_coverage_pct,
        "current_coverage_pct": gate.current_coverage_pct,
        "blocked": list(BLOCKED_ENRICHMENT),
    }


def migrate_dual_date_columns(session: Session) -> dict[str, Any]:
    """Add race_date_jalali / extracted_at columns if missing (SQLite-safe)."""
    added: list[str] = []
    binds = session.connection()
    for table, col, decl in (
        ("raw_races", "race_date_jalali", "VARCHAR(32)"),
        ("wh_races", "race_date_jalali", "VARCHAR(32)"),
        ("wh_races", "extracted_at", "DATETIME"),
    ):
        cols = {r[1] for r in binds.exec_driver_sql(f"PRAGMA table_info({table})")}
        if col not in cols:
            binds.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
            added.append(f"{table}.{col}")
    session.flush()
    return {"altered": added}


def backfill_jalali_dates(session: Session) -> dict[str, int]:
    """Populate race_date_jalali from race_date without deleting existing rows."""
    raw_n = session.connection().exec_driver_sql(
        "SELECT COUNT(*) FROM raw_races WHERE race_date IS NOT NULL AND "
        "(race_date_jalali IS NULL OR race_date_jalali='')"
    ).scalar()
    wh_n = session.connection().exec_driver_sql(
        "SELECT COUNT(*) FROM wh_races WHERE race_date IS NOT NULL AND "
        "(race_date_jalali IS NULL OR race_date_jalali='')"
    ).scalar()
    # row-by-row for portability
    raw_updated = 0
    for rid, rd in session.connection().exec_driver_sql(
        "SELECT id, race_date FROM raw_races WHERE race_date IS NOT NULL AND "
        "(race_date_jalali IS NULL OR race_date_jalali='')"
    ):
        j = jalali_string(rd)
        if j:
            session.connection().exec_driver_sql(
                "UPDATE raw_races SET race_date_jalali=? WHERE id=?",
                (j, rid),
            )
            raw_updated += 1
    wh_updated = 0
    for rid, rd in session.connection().exec_driver_sql(
        "SELECT id, race_date FROM wh_races WHERE race_date IS NOT NULL AND "
        "(race_date_jalali IS NULL OR race_date_jalali='')"
    ):
        j = jalali_string(rd)
        if j:
            session.connection().exec_driver_sql(
                "UPDATE wh_races SET race_date_jalali=? WHERE id=?",
                (j, rid),
            )
            wh_updated += 1
    session.flush()
    return {
        "raw_needed": int(raw_n or 0),
        "wh_needed": int(wh_n or 0),
        "raw_updated": raw_updated,
        "wh_updated": wh_updated,
    }


def record_conflict(
    session: Session,
    *,
    entity_type: str,
    entity_key: str,
    field_name: str,
    source_a: str,
    value_a: Any,
    source_url_a: str | None,
    source_b: str,
    value_b: Any,
    source_url_b: str | None,
) -> CovSourceConflict:
    pri_rows = session.scalars(select(CovSourcePriority)).all()
    pri = {r.source: r.priority_rank for r in pri_rows}
    pref = preferred_source(source_a, source_b, pri)
    row = CovSourceConflict(
        entity_type=entity_type,
        entity_key=entity_key,
        field_name=field_name,
        source_a=source_a,
        value_a_json=value_a,
        source_url_a=source_url_a,
        source_b=source_b,
        value_b_json=value_b,
        source_url_b=source_url_b,
        preferred_source=pref,
        status="open" if pref is None else "resolved_by_priority",
    )
    session.add(row)
    session.flush()
    return row


def _stage_report(
    *,
    stage: str,
    before: dict[str, Any],
    after: dict[str, Any],
    new: int = 0,
    duplicates_skipped: int = 0,
    modified: int = 0,
    conflicts: int = 0,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = {
        "stage": stage,
        "at_utc": datetime.now(timezone.utc).isoformat(),
        "previous_records": before,
        "new_records": new,
        "duplicates_skipped_not_deleted": duplicates_skipped,
        "modified_records": modified,
        "conflicts_logged": conflicts,
        "after_records": after,
        "still_missing_gaps": after.get("open_missing_gaps"),
        "coverage_note": (
            "Coverage % vs real-world calendar is a proxy; vs known digital sources tracked separately"
        ),
        "extra": extra or {},
    }
    ART.mkdir(parents=True, exist_ok=True)
    path = ART / f"coverage_stage_{stage}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    report["report_path"] = str(path)
    return report


def run_stage(session: Session, stage: str, fn) -> dict[str, Any]:
    run = CovPipelineRun(stage=stage, status="running")
    session.add(run)
    session.flush()
    before = coverage_snapshot(session)
    try:
        result = fn(session)
        after = coverage_snapshot(session)
        report = _stage_report(
            stage=stage,
            before=before,
            after=after,
            new=int(result.get("new", 0)),
            duplicates_skipped=int(result.get("duplicates_skipped", 0)),
            modified=int(result.get("modified", 0)),
            conflicts=int(result.get("conflicts", 0)),
            extra=result,
        )
        # proxy coverage: known-source saturation vs open month gaps
        month_gaps = after.get("open_missing_gaps") or 0
        # crude: fewer open month-scope gaps ⇒ higher (cap)
        proxy = result.get("coverage_pct")
        if proxy is None:
            # heuristic placeholder until calendar census exists
            proxy = max(5.0, min(98.0, 100.0 - (month_gaps * 0.05)))
        gate = ensure_enrichment_gate(session, coverage_pct=float(proxy))
        report["enrichment_gate"] = gate
        report["coverage_pct_proxy"] = proxy
        run.status = "success"
        run.finished_at = datetime.now(timezone.utc)
        run.metrics_json = report
        run.report_path = report["report_path"]
        session.commit()
        return report
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.finished_at = datetime.now(timezone.utc)
        run.metrics_json = {"error": str(exc)}
        session.commit()
        raise


def stage_normalize(session: Session) -> dict[str, Any]:
    ensure_source_priorities(session)
    mig = migrate_dual_date_columns(session)
    # need new session state after DDL
    bf = backfill_jalali_dates(session)
    return {"new": 0, "modified": bf["raw_updated"] + bf["wh_updated"], "migrate": mig, "backfill": bf}


def stage_validate_mark_gaps(session: Session) -> dict[str, Any]:
    gaps = detect_and_upsert_missing_gaps(session)
    return {"new": gaps["upserted_or_refreshed"], "modified": 0, "gaps": gaps}


def week_id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    m = re.search(r"/racecards/([A-Za-z0-9]+)", url)
    return m.group(1) if m else None
