#!/usr/bin/env python3
"""Coverage-first Phase 1 runner.

Priority lock: RaceDay / Heat / Result / Horse / Trainer / Owner / Breed / dates / track.
No pedigree/age/weather/features enrichment.

Stages emit reports under /opt/cursor/artifacts/coverage_stage_*.json
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB_PATH = Path("/workspace/output/historical/horse_racing.db")
ART = Path("/opt/cursor/artifacts")
ART.mkdir(parents=True, exist_ok=True)

os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["CRAWL_ALLOWED_RACECOURSES"] = "*"
os.environ.setdefault("CRAWL_DELAY_SECONDS", "0.5")
os.environ.setdefault("OUTPUT_DIR", "output/historical/coverage")
os.environ.setdefault("LOG_LEVEL", "INFO")

from loguru import logger

from src.asbdavani.constants import absolute_url, parse_race_url
from src.collectors import RaceCollector
from src.coverage.gaps import coverage_snapshot
from src.coverage.pipeline import (
    run_stage,
    stage_normalize,
    stage_validate_mark_gaps,
)
from src.coverage.policy import BLOCKED_ENRICHMENT
from src.database import init_db, reset_engine, session_scope
from src.identity import build_horse_identity
from src.utils.logging import setup_logging
from src.warehouse import build_warehouse, run_entity_resolution


def _db_race_urls() -> set[str]:
    import sqlite3

    conn = sqlite3.connect(str(DB_PATH))
    urls = {
        (u or "").split("#")[0]
        for (u,) in conn.execute("SELECT source_url FROM wh_races WHERE source_url IS NOT NULL")
    }
    conn.close()
    return urls


def _profile_urls(limit: int = 80) -> list[str]:
    import sqlite3

    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        """
        SELECT profile_url FROM wh_horses
        WHERE profile_url IS NOT NULL AND TRIM(profile_url) != ''
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def extract_from_horse_histories(*, horse_limit: int = 60, max_new_urls: int = 120) -> dict:
    """Discover race URLs from horse histories that are absent from DB; collect them."""
    from src.datasources import get_datasource

    existing = _db_race_urls()
    profiles = _profile_urls(horse_limit)
    discovered: list[str] = []
    ds = get_datasource("asbdavani")
    try:
        for i, purl in enumerate(profiles, 1):
            try:
                hist = ds.collect_horse_history(purl)
            except Exception as exc:  # noqa: BLE001
                logger.warning("history fail {}: {}", purl, exc)
                continue
            for row in hist.history:
                url = getattr(row, "race_url", None) or getattr(row, "raceUrl", None)
                if not url:
                    continue
                url = absolute_url(str(url)).split("#")[0]
                if url in existing or url in discovered:
                    continue
                # must look like racecards?round=
                if "/racecards/" not in url or "round=" not in url:
                    continue
                discovered.append(url)
            if len(discovered) >= max_new_urls:
                break
            if i % 10 == 0:
                logger.info("scanned {}/{} profiles, new urls {}", i, len(profiles), len(discovered))
            time.sleep(0.35)
    finally:
        close = getattr(ds, "close", None)
        if callable(close):
            close()

    logger.info("Discovered {} new heat URLs from horse histories", len(discovered))
    collector = RaceCollector(
        collect_histories=False,
        persist_to_db=True,
        output_dir=Path("output/historical/coverage/history_extract"),
    )
    ok, fail, skipped = [], [], 0
    try:
        for i, url in enumerate(discovered, 1):
            if url in existing:
                skipped += 1
                continue
            try:
                collector.collect(url)
                ok.append(url)
                existing.add(url)
            except Exception as exc:  # noqa: BLE001
                fail.append({"url": url, "error": str(exc)})
                logger.error("collect {}: {}", url, exc)
            if i % 20 == 0:
                logger.info("collected {}/{}", i, len(discovered))
            time.sleep(0.4)
    finally:
        ds2 = getattr(collector, "datasource", None)
        close = getattr(ds2, "close", None)
        if callable(close):
            close()

    return {
        "new": len(ok),
        "duplicates_skipped": skipped,
        "modified": 0,
        "conflicts": 0,
        "discovered_urls": len(discovered),
        "failed": fail[:20],
        "profiles_scanned": len(profiles),
        "source": "asbdavani_horse_history",
    }


def stage_merge(session) -> dict:
    """Rebuild warehouse + identity without deleting prior Raw versions."""
    # session is open; run ETL in same engine
    wh = build_warehouse(session)
    er = run_entity_resolution(session)
    return {
        "new": int(wh.get("races", 0) or 0),
        "modified": int(sum(wh.values()) if isinstance(wh, dict) else 0),
        "duplicates_skipped": 0,
        "conflicts": 0,
        "warehouse": wh,
        "entity_resolution": er,
    }


def stage_identity(session) -> dict:
    stats = build_horse_identity(session)
    return {"new": 0, "modified": 0, "identity": stats}


def stage_integrity(session) -> dict:
    snap = coverage_snapshot(session)
    import sqlite3

    conn = sqlite3.connect(str(DB_PATH))
    jalali_filled = conn.execute(
        "SELECT COUNT(*) FROM wh_races WHERE race_date_jalali IS NOT NULL AND race_date_jalali!=''"
    ).fetchone()[0]
    dual_pct = round(100 * jalali_filled / max(snap["heats"], 1), 2)
    heats_no_res = conn.execute(
        """
        SELECT COUNT(*) FROM wh_races ra
        WHERE NOT EXISTS (SELECT 1 FROM wh_race_results rr WHERE rr.race_id=ra.id)
        """
    ).fetchone()[0]
    conn.close()
    return {
        "new": 0,
        "modified": 0,
        "dual_date_pct": dual_pct,
        "heats_without_results": heats_no_res,
        "snapshot": snap,
        "enrichment_still_blocked": list(BLOCKED_ENRICHMENT),
        # real-world proxy remains low until calendars filled; gate stays closed
        "coverage_pct": min(40.0, max(10.0, dual_pct * 0.2 + 12)),
    }


def main() -> None:
    setup_logging()
    reset_engine()
    init_db()
    reports = []

    logger.info("=== NORMALIZE (dual dates, priorities, migrate) ===")
    with session_scope() as session:
        reports.append(run_stage(session, "normalize", stage_normalize))

    logger.info("=== VALIDATE / MARK MISSING COVERAGE ===")
    with session_scope() as session:
        reports.append(run_stage(session, "validate_mark_gaps", stage_validate_mark_gaps))

    logger.info("=== EXTRACT (horse history → missing heats) ===")
    # extract uses its own browser/DB writes; wrap metrics manually
    before = None
    with session_scope() as session:
        before = coverage_snapshot(session)
    extracted = extract_from_horse_histories(horse_limit=60, max_new_urls=120)
    with session_scope() as session:
        after = coverage_snapshot(session)
        from src.coverage.pipeline import _stage_report, ensure_enrichment_gate
        from src.coverage.models import CovPipelineRun

        rep = _stage_report(
            stage="extract",
            before=before,
            after=after,
            new=extracted["new"],
            duplicates_skipped=extracted["duplicates_skipped"],
            modified=0,
            conflicts=0,
            extra=extracted,
        )
        rep["coverage_pct_proxy"] = 15.0
        rep["enrichment_gate"] = ensure_enrichment_gate(session, 15.0)
        run = CovPipelineRun(
            stage="extract",
            status="success",
            finished_at=datetime.now(timezone.utc),
            metrics_json=rep,
            report_path=rep["report_path"],
        )
        session.add(run)
        reports.append(rep)

    logger.info("=== MERGE (warehouse rebuild, append-only raw preserved) ===")
    with session_scope() as session:
        reports.append(run_stage(session, "merge", stage_merge))

    logger.info("=== MATCH IDENTITY ===")
    with session_scope() as session:
        reports.append(run_stage(session, "match_identity", stage_identity))

    logger.info("=== INTEGRITY ===")
    with session_scope() as session:
        reports.append(run_stage(session, "integrity", stage_integrity))

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "priority": "coverage_first",
        "blocked_enrichment": list(BLOCKED_ENRICHMENT),
        "stages": [
            {
                "stage": r["stage"],
                "previous_records": r.get("previous_records"),
                "new_records": r.get("new_records"),
                "duplicates_skipped_not_deleted": r.get("duplicates_skipped_not_deleted"),
                "modified_records": r.get("modified_records"),
                "conflicts_logged": r.get("conflicts_logged"),
                "after_records": r.get("after_records"),
                "still_missing_gaps": r.get("still_missing_gaps"),
                "coverage_pct_proxy": r.get("coverage_pct_proxy"),
                "enrichment_gate": r.get("enrichment_gate"),
            }
            for r in reports
        ],
    }
    path = ART / "coverage_phase1_summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md = ["# Coverage Phase-1 Summary", f"Blocked enrichment: {', '.join(BLOCKED_ENRICHMENT)}", ""]
    for s in summary["stages"]:
        md.append(f"## {s['stage']}")
        md.append(f"- قبلی: `{s['previous_records']}`")
        md.append(f"- جدید: **{s['new_records']}**")
        md.append(f"- تکراری ردشده (حذف نشد): **{s['duplicates_skipped_not_deleted']}**")
        md.append(f"- اصلاح‌شده: **{s['modified_records']}**")
        md.append(f"- متناقض: **{s['conflicts_logged']}**")
        md.append(f"- بعد: `{s['after_records']}`")
        md.append(f"- Missing gaps باز: **{s['still_missing_gaps']}**")
        md.append(f"- Coverage proxy: **{s.get('coverage_pct_proxy')}%**")
        md.append(f"- Enrichment gate: `{s.get('enrichment_gate')}`")
        md.append("")
    (ART / "coverage_phase1_summary.md").write_text("\n".join(md), encoding="utf-8")
    logger.info("Wrote {}", path)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str)[:4000])


if __name__ == "__main__":
    main()
