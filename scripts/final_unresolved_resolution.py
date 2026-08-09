#!/usr/bin/env python3
"""FINAL UNRESOLVED RESOLUTION — prioritize, investigate P0/P1, classify, integrity.

Source of Truth: Coverage Matrix UNRESOLVED cells (year × month × city).
Never treat empty DB as No-Race. No PHASE5 enrichment.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import jdatetime
from loguru import logger
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.collectors.race_collector import RaceCollector
from src.coverage.matrix import build_coverage_matrix, write_matrix_artifacts
from src.coverage.models import CovEnrichmentGate
from src.coverage.pipeline import ensure_enrichment_gate
from src.database import init_db, session_scope
from src.identity import build_horse_identity
from src.racecourses.schema import seed_track_configurations
from src.racecourses.track_config import resolve_track_configuration
from src.warehouse import build_warehouse, run_entity_resolution
from src.warehouse.models import WhRace, WhRaceResult

ART = Path("/opt/cursor/artifacts")
ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path("/workspace/output/historical/horse_racing.db")
DEFAULT_DB = f"sqlite:///{DB_PATH}"
MATRIX_FULL = ART / "coverage_matrix_full.json"
HISTORY_PATH = Path("/tmp/history_evidence.json")
LEDGER_PATH = ART / "final_unresolved_ledger.json"


def norm_city(s: str | None) -> str:
    if not s:
        return ""
    t = str(s).replace("\u200c", " ").replace("\u200d", "")
    return re.sub(r"\s+", " ", t).strip()


def cell_id(y: int, m: int, city: str) -> str:
    return f"{y}-{m:02d}-{norm_city(city)}"


def recount() -> dict[str, int]:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        return {
            "race_days": conn.execute(
                "SELECT COUNT(*) FROM ("
                " SELECT DISTINCT race_date, track FROM wh_races "
                " WHERE race_date IS NOT NULL AND track IS NOT NULL)"
            ).fetchone()[0],
            "heats": conn.execute("SELECT COUNT(*) FROM wh_races").fetchone()[0],
            "results": conn.execute("SELECT COUNT(*) FROM wh_race_results").fetchone()[0],
            "horses": conn.execute("SELECT COUNT(*) FROM wh_horses").fetchone()[0],
        }
    finally:
        conn.close()


def wh_cell_heats() -> dict[tuple[int, int, str], int]:
    out: dict[tuple[int, int, str], int] = defaultdict(int)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        for rd, tr in conn.execute(
            "SELECT race_date, track FROM wh_races WHERE race_date IS NOT NULL AND track IS NOT NULL"
        ):
            g = date.fromisoformat(str(rd)[:10])
            jd = jdatetime.date.fromgregorian(date=g)
            out[(jd.year, jd.month, norm_city(tr))] += 1
    finally:
        conn.close()
    return out


def city_month_priors() -> dict[str, set[int]]:
    """Months each city has raced historically (any heat)."""
    priors: dict[str, set[int]] = defaultdict(set)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        for rd, tr in conn.execute(
            "SELECT race_date, track FROM wh_races WHERE race_date IS NOT NULL AND track IS NOT NULL"
        ):
            g = date.fromisoformat(str(rd)[:10])
            jd = jdatetime.date.fromgregorian(date=g)
            priors[norm_city(tr)].add(jd.month)
    finally:
        conn.close()
    return priors


def load_history_index() -> dict[tuple[int, int, str], list[dict]]:
    if not HISTORY_PATH.exists():
        return {}
    data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    idx: dict[tuple[int, int, str], list[dict]] = defaultdict(list)
    for key, rows in (data.get("cells") or {}).items():
        parts = str(key).split("|")
        if len(parts) != 3 or parts[2] == "*":
            continue
        try:
            y, m = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        idx[(y, m, norm_city(parts[2]))].extend(rows)
    return idx


def prioritize_unresolved(
    unresolved: list[dict[str, Any]],
    *,
    wh: dict[tuple[int, int, str], int],
    hist: dict[tuple[int, int, str], list[dict]],
    priors: dict[str, set[int]],
    months_with_race: set[tuple[int, int]],
) -> list[dict[str, Any]]:
    """Assign P0–P3 + evidence fields. Never invent No-Race."""
    now = datetime.now(timezone.utc).isoformat()
    ledger: list[dict[str, Any]] = []

    for c in unresolved:
        y, m, city = int(c["jalali_year"]), int(c["jalali_month"]), norm_city(c["city"])
        key = (y, m, city)
        heats = wh.get(key, 0)
        if heats > 0:
            # Already filled since matrix snapshot — mark resolved race
            ledger.append(
                {
                    "Year_Jalali": y,
                    "Month_Jalali": m,
                    "City": city,
                    "Cell_ID": cell_id(y, m, city),
                    "Status": "CONFIRMED_RACE",
                    "Priority": "P0",
                    "Evidence": f"warehouse_already_has_heats={heats}",
                    "Source": "wh_races",
                    "Source_URL": None,
                    "Last_Checked": now,
                    "Confidence": 1.0,
                    "outcome": "already_filled",
                }
            )
            continue

        hist_rows = hist.get(key) or []
        urls = sorted({r.get("url") for r in hist_rows if r.get("url")})
        dates = sorted({r.get("date") for r in hist_rows if r.get("date")})
        season_ok = m in priors.get(city, set())
        active_month = (y, m) in months_with_race

        if urls:
            priority = "P0"
            evidence = (
                f"horse_history_lists_official_starts dates={dates[:8]} "
                f"url_count={len(urls)} heats_evidence={len(hist_rows)}"
            )
            source = "asbdavani_horse_history"
            source_url = urls[0]
            confidence = 0.92
            status = "MISSING_DATA"  # proven race, DB empty — pending extract
        elif season_ok and active_month:
            priority = "P1"
            evidence = (
                "city historically races this Jalali month AND other cities "
                "have CONFIRMED_RACE in same year-month; checkable on asbdavani"
            )
            source = "seasonality+active_month_heuristic"
            source_url = "https://asbdavani.app/racecards"
            confidence = 0.55
            status = "UNRESOLVED"
        elif season_ok:
            priority = "P2"
            evidence = (
                "city historically races this month in other years, but this "
                "year-month has no nationwide CONFIRMED_RACE and no URL proof"
            )
            source = "seasonality_only"
            source_url = None
            confidence = 0.35
            status = "UNRESOLVED"
        else:
            priority = "P3"
            evidence = (
                "city has little/no historical racing in this Jalali month; "
                "no external proof; empty≠no-race"
            )
            source = "none"
            source_url = None
            confidence = 0.15
            status = "UNRESOLVED"

        ledger.append(
            {
                "Year_Jalali": y,
                "Month_Jalali": m,
                "City": city,
                "Cell_ID": cell_id(y, m, city),
                "Status": status,
                "Priority": priority,
                "Evidence": evidence,
                "Source": source,
                "Source_URL": source_url,
                "Last_Checked": now,
                "Confidence": confidence,
                "urls": urls,
                "outcome": "pending",
            }
        )
    return ledger


def extract_urls(urls: list[str], *, out_dir: Path, sleep_s: float = 0.3) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    collector = RaceCollector(
        collect_histories=False, persist_to_db=True, output_dir=out_dir
    )
    ok: list[str] = []
    fail: list[dict[str, str]] = []
    try:
        for i, url in enumerate(urls, 1):
            try:
                collector.collect(url)
                ok.append(url)
            except Exception as exc:  # noqa: BLE001
                fail.append({"url": url, "error": str(exc)[:400]})
                logger.error("extract fail {}: {}", url, exc)
            if i % 20 == 0:
                logger.info("extract {}/{} ok={} fail={}", i, len(urls), len(ok), len(fail))
            time.sleep(sleep_s)
    finally:
        close = getattr(getattr(collector, "datasource", None), "close", None)
        if callable(close):
            close()
    return {"ok": ok, "failed": fail}


def rebuild_wh() -> None:
    with session_scope() as session:
        build_warehouse(session)
        build_horse_identity(session)
        run_entity_resolution(session)


def run_integrity(label: str) -> dict[str, Any]:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "full_integrity_check", ROOT / "scripts" / "full_integrity_check.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        pre = mod.audit(conn)
        repairs = {
            "natural_heat_dups": mod.fix_natural_heat_duplicates(conn, pre),
            "date_jalali_fixed": mod.fix_date_jalali(conn),
            "wrong_city_fixed": mod.fix_wrong_city_codes(conn),
        }
        post = mod.audit(conn)
        return {
            "label": label,
            "pre_duplicates": pre["duplicate_total"],
            "post_duplicates": post["duplicate_total"],
            "pre_broken": pre["broken_relation_total"],
            "post_broken": post["broken_relation_total"],
            "date_conflicts": post["date_conflict_total"],
            "source_conflicts": post["source_conflict_total"],
            "repairs": repairs,
            "duplicate_prevented_or_fixed": pre["duplicate_total"] - post["duplicate_total"],
            "integrity_errors": post["duplicate_total"]
            + post["broken_relation_total"]
            + post["date_conflict_total"],
        }
    finally:
        conn.close()


def harvest_for_p1(profiles: int = 200) -> dict[str, Any]:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "investigate_needs_gaps", ROOT / "scripts" / "investigate_needs_gaps.py"
    )
    assert spec and spec.loader
    ni = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ni)
    plist = ni.stratified_profiles(profiles)
    harvested = ni.harvest_histories(plist)
    out = Path("/tmp/history_evidence_final_unresolved.json")
    out.write_text(
        json.dumps(
            {
                "profiles_targeted": len(plist),
                "profiles_scanned_ok": harvested["ok"],
                "errors": harvested["errors"],
                "cells": harvested["cells"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    merged = ni.merge_history_sources(HISTORY_PATH, out)
    HISTORY_PATH.write_text(
        json.dumps(
            {
                "profiles_targeted": "merged_final_unresolved",
                "profiles_scanned_ok": harvested["ok"],
                "errors": harvested["errors"],
                "cells": merged,
                "cell_counts": {k: len(v) for k, v in merged.items()},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return {"profiles": len(plist), "ok": harvested["ok"], "errors": harvested["errors"]}


def track_unknown_report(session: Session) -> dict[str, Any]:
    races = list(session.scalars(select(WhRace).where(WhRace.race_date.is_not(None))).all())
    results = list(session.scalars(select(WhRaceResult)).all())
    res_n: dict[int, int] = defaultdict(int)
    for r in results:
        if r.race_id is not None:
            res_n[int(r.race_id)] += 1

    matched = unmatched = ambiguous = 0
    unknown_by_name: Counter = Counter()
    days: set[tuple] = set()
    for r in races:
        cfg = resolve_track_configuration(
            racecourse_code=r.racecourse_code, track_name=r.track, city=r.track
        )
        if cfg is None:
            unmatched += 1
            unknown_by_name[r.track or "?"] += 1
        else:
            matched += 1
        try:
            g = date.fromisoformat(str(r.race_date)[:10])
            days.add((g.isoformat(), r.track))
        except ValueError:
            pass
    total = len(races)
    return {
        "total_heats": total,
        "matched": matched,
        "unmatched": unmatched,
        "ambiguous": ambiguous,
        "track_match_coverage_pct": round(100.0 * matched / total, 4) if total else None,
        "unknown_raw_names": dict(unknown_by_name),
        "note": (
            "انبارآلوم has no finishing-straight in the provided diagram; "
            "remains UNKNOWN (no guessing)."
            if unknown_by_name
            else "All heats matched to Track Configuration."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", default=DEFAULT_DB)
    ap.add_argument("--harvest", type=int, default=180)
    ap.add_argument("--max-extract", type=int, default=120)
    ap.add_argument("--skip-harvest", action="store_true")
    ap.add_argument("--skip-extract", action="store_true")
    ap.add_argument("--classify-only", action="store_true")
    args = ap.parse_args()

    os.environ.setdefault("CRAWL_ALLOWED_RACECOURSES", "*")
    os.environ.setdefault("DATABASE_URL", args.db_url)
    ART.mkdir(parents=True, exist_ok=True)
    init_db(url=args.db_url)

    before = recount()
    logger.info("before {}", before)

    if not MATRIX_FULL.exists():
        with Session(create_engine(args.db_url)) as session:
            write_matrix_artifacts(build_coverage_matrix(session))

    full = json.loads(MATRIX_FULL.read_text(encoding="utf-8"))
    unresolved = [c for c in full["cells"] if c["status"] == "UNRESOLVED"]
    initial_unresolved = len(unresolved)
    logger.info("matrix UNRESOLVED initial={}", initial_unresolved)

    # months with any CONFIRMED_RACE
    months_with_race = {
        (c["jalali_year"], c["jalali_month"])
        for c in full["cells"]
        if c["status"] == "CONFIRMED_RACE"
    }

    wh = wh_cell_heats()
    priors = city_month_priors()
    hist = load_history_index()

    # Optional harvest to discover new P0
    harvest_info: dict[str, Any] | None = None
    if not args.skip_harvest and not args.classify_only:
        logger.info("harvesting {} profiles for P0 discovery", args.harvest)
        harvest_info = harvest_for_p1(args.harvest)
        hist = load_history_index()

    ledger = prioritize_unresolved(
        unresolved,
        wh=wh,
        hist=hist,
        priors=priors,
        months_with_race=months_with_race,
    )
    pri_counts = Counter(r["Priority"] for r in ledger)
    logger.info("priority counts {}", dict(pri_counts))

    # Extract P0 (+ any P1 that gained URLs after harvest)
    p0 = [r for r in ledger if r["Priority"] == "P0" and r.get("urls")]
    extract_info: dict[str, Any] = {"ok": [], "failed": []}
    integrity_runs: list[dict[str, Any]] = []

    if not args.skip_extract and not args.classify_only and p0:
        urls: list[str] = []
        seen: set[str] = set()
        for r in p0:
            for u in r.get("urls") or []:
                if u not in seen:
                    seen.add(u)
                    urls.append(u)
                if len(urls) >= args.max_extract:
                    break
            if len(urls) >= args.max_extract:
                break
        logger.info("P0 extract urls={}", len(urls))
        extract_info = extract_urls(
            urls, out_dir=Path("output/historical/coverage/final_unresolved_extract")
        )
        rebuild_wh()
        integrity_runs.append(run_integrity("after_p0_extract"))
        wh = wh_cell_heats()

    # Reclassify outcomes after extract
    now = datetime.now(timezone.utc).isoformat()
    resolved_race = resolved_no_race = to_missing = still_unresolved = 0
    for r in ledger:
        y, m, city = r["Year_Jalali"], r["Month_Jalali"], r["City"]
        heats = wh.get((y, m, city), 0)
        r["Last_Checked"] = now
        if heats > 0:
            r["Status"] = "CONFIRMED_RACE"
            r["outcome"] = "resolved_to_race"
            r["Evidence"] = f"extracted_or_present heats_in_db={heats}"
            r["Confidence"] = 1.0
            resolved_race += 1
        elif r["Priority"] == "P0" and r.get("urls") and heats == 0:
            # Still proven missing after extract attempt
            r["Status"] = "MISSING_DATA"
            r["outcome"] = "converted_to_missing_data"
            r["Evidence"] = (
                (r.get("Evidence") or "")
                + "; extract_attempted_but_cell_still_empty_or_urls_partial"
            )
            to_missing += 1
        else:
            # Never invent No-Race
            r["Status"] = "UNRESOLVED"
            r["outcome"] = "still_unresolved"
            still_unresolved += 1

    after = recount()

    # Final matrix + coverage explanation
    engine = create_engine(args.db_url)
    with Session(engine) as session:
        seed_track_configurations(session)
        matrix = build_coverage_matrix(session)
        paths = write_matrix_artifacts(matrix)
        track_val = track_unknown_report(session)
        cov = matrix["coverage"]
        md_left = int(matrix["status_counts"].get("MISSING_DATA") or 0)
        ensure_enrichment_gate(session, coverage_pct=float(cov.get("pct") or 0))
        gate = session.scalar(
            select(CovEnrichmentGate).where(CovEnrichmentGate.name == "secondary")
        )
        if gate is not None:
            gate.current_coverage_pct = float(cov.get("pct") or 0)
            gate.allowed = False  # PHASE5 forbidden until unresolved reduced
            gate.notes = (
                f"proven_coverage={cov.get('display')}; MISSING_DATA={md_left}; "
                f"matrix_UNRESOLVED={matrix['status_counts'].get('UNRESOLVED')}; "
                "PHASE5 blocked; proven≠national historical coverage"
            )
        session.commit()

    if not integrity_runs:
        integrity_runs.append(run_integrity("final_audit"))

    last_integ = integrity_runs[-1]
    delta = {k: after[k] - before[k] for k in after}

    # Coverage meaning
    coverage_meaning = {
        "metric_name": "Proven Race-Obligation Coverage (Coverage Matrix)",
        "formula": "CONFIRMED_RACE / (CONFIRMED_RACE + MISSING_DATA)",
        "value": cov.get("display"),
        "means": (
            "Share of year×month×city cells where a race is *proven* to have "
            "occurred that are already captured in the warehouse. "
            "UNRESOLVED and CONFIRMED_NO_RACE are excluded from the denominator."
        ),
        "does_NOT_mean": (
            "NATIONAL HISTORICAL COVERAGE — i.e. it is NOT the fraction of all "
            "Jalali year×month×city calendar cells historically filled, and NOT "
            "the share of all Iranian racing that ever happened."
        ),
        "matrix_fill_companion": {
            "CONFIRMED_RACE": matrix["status_counts"].get("CONFIRMED_RACE"),
            "MISSING_DATA": matrix["status_counts"].get("MISSING_DATA"),
            "UNRESOLVED": matrix["status_counts"].get("UNRESOLVED"),
            "CONFIRMED_NO_RACE": matrix["status_counts"].get("CONFIRMED_NO_RACE"),
            "total_cells": matrix["total_cells"],
            "grid_fill_pct": round(
                100.0
                * matrix["status_counts"].get("CONFIRMED_RACE", 0)
                / max(1, matrix["total_cells"] - matrix["status_counts"].get("CONFIRMED_NO_RACE", 0)),
                4,
            ),
        },
    }

    entity_resolution_ready = (
        last_integ["integrity_errors"] == 0
        and md_left == 0
        and after["heats"] > 0
    )

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "note_on_303": (
            f"User cited 303 UNRESOLVED; Coverage Matrix Source of Truth currently "
            f"has {initial_unresolved} UNRESOLVED city-month cells. This run "
            f"processes the full matrix set ({initial_unresolved})."
        ),
        "UNRESOLVED_initial": initial_unresolved,
        "priority_counts": dict(pri_counts),
        "P0": pri_counts.get("P0", 0),
        "P1": pri_counts.get("P1", 0),
        "P2": pri_counts.get("P2", 0),
        "P3": pri_counts.get("P3", 0),
        "Resolved_to_Race": resolved_race,
        "Resolved_to_No_Race": resolved_no_race,
        "Converted_to_Missing_Data": to_missing,
        "Still_Unresolved": still_unresolved,
        "before": before,
        "after": after,
        "delta": delta,
        "Race_Day_new": delta["race_days"],
        "Heat_new": delta["heats"],
        "Result_new": delta["results"],
        "Duplicate_prevented": last_integ.get("duplicate_prevented_or_fixed", 0),
        "Integrity_errors": last_integ.get("integrity_errors", 0),
        "integrity_runs": integrity_runs,
        "harvest": harvest_info,
        "extract": {
            "ok": len(extract_info.get("ok") or []),
            "failed": len(extract_info.get("failed") or []),
        },
        "coverage": coverage_meaning,
        "matrix_status_counts": matrix["status_counts"],
        "track_validation": track_val,
        "entity_resolution_ready": entity_resolution_ready,
        "entity_resolution_ready_reason": (
            "Integrity clean, MISSING_DATA=0, warehouse populated — "
            "safe for Entity Resolution on existing identities. "
            "PHASE5 (prediction/ranking/pedigree/weather/betting) still forbidden "
            "while large UNRESOLVED calendar remains."
            if entity_resolution_ready
            else "Not ready: integrity errors or open MISSING_DATA remain."
        ),
        "phase5_blocked": True,
        "matrix_artifacts": paths,
    }

    # Persist ledger (strip bulky urls in csv)
    LEDGER_PATH.write_text(json.dumps({"rows": ledger, "report": report}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    csv_path = ART / "final_unresolved_ledger.csv"
    fields = [
        "Year_Jalali",
        "Month_Jalali",
        "City",
        "Cell_ID",
        "Status",
        "Priority",
        "Evidence",
        "Source",
        "Source_URL",
        "Last_Checked",
        "Confidence",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in ledger:
            w.writerow(row)

    md = [
        "# FINAL UNRESOLVED RESOLUTION",
        "",
        report["note_on_303"],
        "",
        f"UNRESOLVED اولیه = **{initial_unresolved}**",
        "",
        f"- P0: **{pri_counts.get('P0', 0)}**",
        f"- P1: **{pri_counts.get('P1', 0)}**",
        f"- P2: **{pri_counts.get('P2', 0)}**",
        f"- P3: **{pri_counts.get('P3', 0)}**",
        "",
        f"- Resolved to Race: **{resolved_race}**",
        f"- Resolved to No-Race: **{resolved_no_race}**",
        f"- Converted to Missing Data: **{to_missing}**",
        f"- Still Unresolved: **{still_unresolved}**",
        "",
        f"- Race Day جدید: **{delta['race_days']}**",
        f"- Heat جدید: **{delta['heats']}**",
        f"- Result جدید: **{delta['results']}**",
        "",
        f"- Duplicate prevented: **{last_integ.get('duplicate_prevented_or_fixed', 0)}**",
        f"- Integrity errors: **{last_integ.get('integrity_errors', 0)}**",
        "",
        "## Coverage",
        "",
        f"Proven Coverage = `{cov.get('display')}`",
        "",
        coverage_meaning["means"],
        "",
        f"**Not** National Historical Coverage. Grid cells: "
        f"RACE={matrix['status_counts'].get('CONFIRMED_RACE')} "
        f"MD={matrix['status_counts'].get('MISSING_DATA')} "
        f"UNRESOLVED={matrix['status_counts'].get('UNRESOLVED')} "
        f"NO_RACE={matrix['status_counts'].get('CONFIRMED_NO_RACE')}.",
        "",
        "## Track",
        "",
        f"Track Match Coverage: **{track_val.get('track_match_coverage_pct')}%** "
        f"(matched={track_val.get('matched')} unmatched={track_val.get('unmatched')} "
        f"ambiguous={track_val.get('ambiguous')})",
        "",
        track_val.get("note") or "",
        "",
        f"## Entity Resolution ready? **{'YES' if entity_resolution_ready else 'NO'}**",
        "",
        report["entity_resolution_ready_reason"],
        "",
        "PHASE5 still blocked.",
    ]
    md_path = ART / "final_unresolved_resolution.md"
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    (ART / "final_unresolved_resolution.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print(md_path.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
