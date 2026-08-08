#!/usr/bin/env python3
"""Continue from Coverage Matrix checkpoint: P0 MISSING_DATA → integrity → P1 batch.

Does NOT redo already-filled cells. No enrichment / ranking / prediction.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, parse_qs

import jdatetime
from loguru import logger
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.collectors.race_collector import RaceCollector
from src.coverage.matrix import build_coverage_matrix, write_matrix_artifacts
from src.coverage.models import CovEnrichmentGate, CovMissingGap
from src.coverage.pipeline import ensure_enrichment_gate
from src.database import init_db
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


def run_integrity_batch(label: str) -> dict[str, Any]:
    """PHASE 2: audit + safe fixes after a coverage batch."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "full_integrity_check",
        ROOT / "scripts" / "full_integrity_check.py",
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
        counts = mod.recount(conn)
        return {
            "label": label,
            "pre": {
                "duplicates": pre["duplicate_total"],
                "broken": pre["broken_relation_total"],
                "date": pre["date_conflict_total"],
                "source": pre["source_conflict_total"],
                "kinds": dict(pre["counts"]),
            },
            "post": {
                "duplicates": post["duplicate_total"],
                "broken": post["broken_relation_total"],
                "date": post["date_conflict_total"],
                "source": post["source_conflict_total"],
                "kinds": dict(post["counts"]),
            },
            "repairs": repairs,
            "db": counts,
        }
    finally:
        conn.close()


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


def load_missing_data_urls() -> tuple[list[dict[str, Any]], list[str]]:
    if not MATRIX_FULL.exists():
        raise FileNotFoundError(MATRIX_FULL)
    full = json.loads(MATRIX_FULL.read_text(encoding="utf-8"))
    mds = [c for c in full["cells"] if c["status"] == "MISSING_DATA"]
    urls: list[str] = []
    seen: set[str] = set()
    for c in mds:
        for u in c.get("source_urls") or []:
            if u and u not in seen:
                seen.add(u)
                urls.append(u)
        # also proving_url
        pu = c.get("proving_url")
        if pu and pu not in seen:
            seen.add(pu)
            urls.append(pu)
    return mds, urls


def extract_urls(urls: list[str], *, out_dir: Path, sleep_s: float = 0.3) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    collector = RaceCollector(
        collect_histories=False, persist_to_db=True, output_dir=out_dir
    )
    ok: list[str] = []
    fail: list[dict[str, str]] = []
    tracks: Counter = Counter()
    try:
        for i, url in enumerate(urls, 1):
            try:
                paths = collector.collect(url)
                ok.append(url)
                # best-effort track from last Race.json
                race_path = paths.get("Race.json")
                if race_path and Path(race_path).exists():
                    payload = json.loads(Path(race_path).read_text(encoding="utf-8"))
                    tracks[payload.get("track") or "?"] += 1
            except Exception as exc:  # noqa: BLE001
                fail.append({"url": url, "error": str(exc)[:400]})
                logger.error("extract fail {}: {}", url, exc)
            if i % 10 == 0:
                logger.info("extract {}/{} ok={} fail={}", i, len(urls), len(ok), len(fail))
            time.sleep(sleep_s)
    finally:
        close = getattr(getattr(collector, "datasource", None), "close", None)
        if callable(close):
            close()
    return {"ok": ok, "failed": fail, "tracks": dict(tracks)}


def rebuild_wh() -> None:
    logger.info("rebuild warehouse + identity + ER")
    from src.database import session_scope

    with session_scope() as session:
        build_warehouse(session)
        build_horse_identity(session)
        run_entity_resolution(session)


def mark_gaps_filled(session: Session, mds: list[dict[str, Any]], after: dict[str, int]) -> int:
    """Mark city-month gaps resolved when WH now has heats for that cell."""
    filled = 0
    races = list(session.scalars(select(WhRace).where(WhRace.race_date.is_not(None))).all())
    by_cell: dict[tuple[int, int, str], int] = defaultdict(int)
    for r in races:
        try:
            g = date.fromisoformat(str(r.race_date)[:10])
        except ValueError:
            continue
        jd = jdatetime.date.fromgregorian(date=g)
        city = (r.track or "").replace("\u200c", " ")
        city = " ".join(city.split())
        by_cell[(jd.year, jd.month, city)] += 1

    for c in mds:
        y, m, city = int(c["jalali_year"]), int(c["jalali_month"]), c["city"]
        heats = by_cell.get((y, m, city), 0)
        if heats <= 0:
            continue
        # update gap ledger if present
        gaps = session.scalars(
            select(CovMissingGap).where(
                CovMissingGap.jalali_year == y,
                CovMissingGap.jalali_month == m,
            )
        ).all()
        for g in gaps:
            g_track = (g.track or "").replace("\u200c", " ")
            g_track = " ".join(g_track.split()) if g_track else None
            if g.scope_type == "city_month" and g_track == city:
                if g.status != "resolved_filled":
                    g.status = "resolved_filled"
                    g.notes = (g.notes or "") + f"; filled_checkpoint heats={heats}"
                    filled += 1
            elif g.scope_type == "month" and g_track in (None, "", city):
                # month-scope: only if this was the MD proof city — leave unresolved months alone
                pass
    session.flush()
    return filled


def track_validation(session: Session) -> dict[str, Any]:
    races = list(session.scalars(select(WhRace).where(WhRace.race_date.is_not(None))).all())
    results = list(session.scalars(select(WhRaceResult)).all())
    res_by_race: dict[int, int] = defaultdict(int)
    for res in results:
        if res.race_id is not None:
            res_by_race[int(res.race_id)] += 1

    # raw track name variants per matched track_id
    by_id: dict[str, dict[str, Any]] = {}
    unmatched: list[dict[str, Any]] = []
    ambiguous = 0  # reserved: never guess; synthetic codes without config

    for r in races:
        cfg = resolve_track_configuration(
            racecourse_code=r.racecourse_code,
            track_name=r.track,
            city=r.track,
        )
        if cfg is None:
            unmatched.append(
                {
                    "track_raw": r.track,
                    "racecourse_code": r.racecourse_code,
                    "race_id": r.id,
                }
            )
            continue
        bucket = by_id.setdefault(
            cfg.track_id,
            {
                "track_id": cfg.track_id,
                "track_name": cfg.track_name,
                "city": cfg.city,
                "straight_length_m": cfg.straight_length_m,
                "raw_names": Counter(),
                "codes": Counter(),
                "race_days": set(),
                "heats": 0,
                "results": 0,
            },
        )
        bucket["raw_names"][r.track or "?"] += 1
        bucket["codes"][r.racecourse_code or "?"] += 1
        bucket["heats"] += 1
        bucket["results"] += res_by_race.get(int(r.id), 0)
        try:
            g = date.fromisoformat(str(r.race_date)[:10])
            bucket["race_days"].add((g.isoformat(), r.track))
        except ValueError:
            pass

    tracks_out = []
    for tid, b in sorted(by_id.items(), key=lambda x: -x[1]["heats"]):
        tracks_out.append(
            {
                "track_id": tid,
                "track_name": b["track_name"],
                "city": b["city"],
                "straight_length_m": b["straight_length_m"],
                "total_race_days": len(b["race_days"]),
                "total_heats": b["heats"],
                "total_results": b["results"],
                "matched": b["heats"],
                "raw_name_variants": dict(b["raw_names"]),
                "code_variants": dict(b["codes"]),
            }
        )

    unmatched_names = Counter(u["track_raw"] for u in unmatched)
    total_heats = len(races)
    matched_heats = sum(t["total_heats"] for t in tracks_out)
    return {
        "tracks": tracks_out,
        "totals": {
            "heats": total_heats,
            "matched_heats": matched_heats,
            "unmatched_heats": len(unmatched),
            "ambiguous_heats": ambiguous,
            "track_match_coverage_pct": round(100.0 * matched_heats / total_heats, 4)
            if total_heats
            else None,
            "races_without_track_configuration": len(unmatched),
        },
        "unmatched_raw_names": dict(unmatched_names),
    }


def p1_history_leads(limit: int = 40) -> list[dict[str, Any]]:
    """P1: UNRESOLVED cells that still have history evidence and empty WH — treat as new MD."""
    hist_path = Path("/tmp/history_evidence.json")
    if not hist_path.exists() or not MATRIX_FULL.exists():
        return []
    hist = json.loads(hist_path.read_text(encoding="utf-8"))
    full = json.loads(MATRIX_FULL.read_text(encoding="utf-8"))
    unresolved = {
        (c["jalali_year"], c["jalali_month"], c["city"]): c
        for c in full["cells"]
        if c["status"] == "UNRESOLVED"
    }
    leads: list[dict[str, Any]] = []
    for key, rows in (hist.get("cells") or {}).items():
        parts = str(key).split("|")
        if len(parts) != 3 or parts[2] == "*":
            continue
        y, m = int(parts[0]), int(parts[1])
        city = " ".join(parts[2].replace("\u200c", " ").split())
        if (y, m, city) not in unresolved:
            continue
        urls = sorted({r.get("url") for r in rows if r.get("url")})
        dates = sorted({r.get("date") for r in rows if r.get("date")})
        if not urls:
            continue
        leads.append(
            {
                "jalali_year": y,
                "jalali_month": m,
                "city": city,
                "urls": urls,
                "dates": dates,
                "confidence": 0.92,
                "source": "asbdavani_horse_history",
            }
        )
    leads.sort(key=lambda x: (-x["jalali_year"], -x["jalali_month"], x["city"]))
    return leads[:limit]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", default=DEFAULT_DB)
    ap.add_argument("--skip-extract", action="store_true")
    ap.add_argument("--skip-p0", action="store_true", help="Skip P0 MISSING_DATA extract (raw already ingested)")
    ap.add_argument("--p1-limit", type=int, default=30, help="Max new P1 MD URL heats to extract")
    ap.add_argument("--skip-p1", action="store_true")
    args = ap.parse_args()

    os.environ.setdefault("CRAWL_ALLOWED_RACECOURSES", "*")
    os.environ.setdefault("DATABASE_URL", args.db_url)
    ART.mkdir(parents=True, exist_ok=True)
    init_db(url=args.db_url)

    before = recount()
    logger.info("checkpoint before {}", before)

    mds, md_urls = load_missing_data_urls()
    logger.info("P0 MISSING_DATA cells={} urls={}", len(mds), len(md_urls))

    extract_report: dict[str, Any] = {"p0": None, "p1": None}
    integrity_runs: list[dict[str, Any]] = []
    do_p0 = (not args.skip_extract) and (not args.skip_p0) and bool(md_urls)
    if do_p0:
        extract_report["p0"] = extract_urls(
            md_urls,
            out_dir=Path("output/historical/coverage/p0_missing_data_extract"),
        )
        logger.info(
            "P0 extract ok={} fail={} tracks={}",
            len(extract_report["p0"]["ok"]),
            len(extract_report["p0"]["failed"]),
            extract_report["p0"]["tracks"],
        )
        rebuild_wh()
        integ = run_integrity_batch("after_p0")
        integrity_runs.append(integ)
        extract_report["p0_integrity"] = integ
    elif args.skip_p0 and md_urls:
        logger.info("skip-p0: rebuilding WH from already-ingested raw")
        rebuild_wh()
        integ = run_integrity_batch("after_p0_rebuild")
        integrity_runs.append(integ)
        extract_report["p0_integrity"] = integ
        extract_report["p0"] = {"ok": [], "failed": [], "tracks": {}, "note": "skipped_extract_rebuilt_wh"}

    # P1: history-proven unresolved → extract limited batch
    engine = create_engine(args.db_url)
    with Session(engine) as session:
        seed_track_configurations(session)
        if mds:
            mark_gaps_filled(session, mds, recount())
        session.commit()

    p1_leads: list[dict[str, Any]] = []
    if not args.skip_p1:
        # refresh matrix after P0 so leads exclude newly filled cells
        with Session(engine) as session:
            mid = build_coverage_matrix(session)
            write_matrix_artifacts(mid)
        p1_leads = p1_history_leads(limit=20)

        # If prior history is exhausted, light stratified harvest for new proof only
        if not p1_leads and not args.skip_extract:
            try:
                from scripts.investigate_needs_gaps import (
                    harvest_histories,
                    stratified_profiles,
                    merge_history_sources,
                    index_history,
                )
            except ImportError:
                import importlib.util

                spec = importlib.util.spec_from_file_location(
                    "investigate_needs_gaps",
                    ROOT / "scripts" / "investigate_needs_gaps.py",
                )
                assert spec and spec.loader
                ni = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(ni)
                harvest_histories = ni.harvest_histories
                stratified_profiles = ni.stratified_profiles
                merge_history_sources = ni.merge_history_sources
                index_history = ni.index_history

            profiles = stratified_profiles(min(200, max(50, args.p1_limit * 4)))
            logger.info("P1 harvest profiles={}", len(profiles))
            harvested = harvest_histories(profiles)
            hist_path = Path("/tmp/history_evidence_checkpoint_p1.json")
            hist_path.write_text(
                json.dumps(
                    {
                        "profiles_targeted": len(profiles),
                        "profiles_scanned_ok": harvested["ok"],
                        "errors": harvested["errors"],
                        "cells": harvested["cells"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            # merge into /tmp/history_evidence.json for lead detection
            prior = Path("/tmp/history_evidence.json")
            merged = merge_history_sources(prior, hist_path)
            prior.write_text(
                json.dumps(
                    {
                        "profiles_targeted": "merged",
                        "profiles_scanned_ok": harvested["ok"],
                        "errors": harvested["errors"],
                        "cells": merged,
                        "cell_counts": {k: len(v) for k, v in merged.items()},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            p1_leads = p1_history_leads(limit=20)
            extract_report["p1_harvest"] = {
                "profiles": len(profiles),
                "ok": harvested["ok"],
                "errors": harvested["errors"],
                "leads_after": len(p1_leads),
            }

        p1_urls: list[str] = []
        seen: set[str] = set()
        for lead in p1_leads:
            for u in lead["urls"]:
                if u not in seen:
                    seen.add(u)
                    p1_urls.append(u)
                if len(p1_urls) >= args.p1_limit:
                    break
            if len(p1_urls) >= args.p1_limit:
                break
        logger.info("P1 leads={} urls={}", len(p1_leads), len(p1_urls))
        if p1_urls and not args.skip_extract:
            extract_report["p1"] = extract_urls(
                p1_urls,
                out_dir=Path("output/historical/coverage/p1_unresolved_extract"),
            )
            rebuild_wh()
            integ = run_integrity_batch("after_p1")
            integrity_runs.append(integ)
            extract_report["p1_integrity"] = integ
            # mark newly filled from leads
            with Session(engine) as session:
                mark_gaps_filled(
                    session,
                    [
                        {
                            "jalali_year": L["jalali_year"],
                            "jalali_month": L["jalali_month"],
                            "city": L["city"],
                        }
                        for L in p1_leads
                    ],
                    recount(),
                )
                session.commit()

    after = recount()
    with Session(engine) as session:
        matrix = build_coverage_matrix(session)
        paths = write_matrix_artifacts(matrix)
        track_val = track_validation(session)
        # gate: proven coverage + zero MD
        cov = matrix["coverage"]
        md_left = int(matrix["status_counts"].get("MISSING_DATA") or 0)
        ensure_enrichment_gate(session, coverage_pct=float(cov.get("pct") or 0))
        gate = session.scalar(
            select(CovEnrichmentGate).where(CovEnrichmentGate.name == "secondary")
        )
        if gate is not None:
            gate.current_coverage_pct = float(cov.get("pct") or 0)
            gate.allowed = bool(
                (cov.get("pct") or 0) >= (gate.min_coverage_pct or 70) and md_left == 0
            )
            gate.notes = (
                "checkpoint continue; Coverage=CONFIRMED_RACE/(RACE+MISSING_DATA); "
                f"MISSING_DATA_open={md_left}; PHASE5 enrichment blocked"
            )
        session.commit()

    last_integ = integrity_runs[-1] if integrity_runs else run_integrity_batch("final_audit_only")
    dup_broken = {
        "duplicates": last_integ["post"]["duplicates"],
        "broken_relations": last_integ["post"]["broken"],
        "date_conflicts": last_integ["post"]["date"],
        "source_conflicts": last_integ["post"]["source"],
    }

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "before": before,
        "after": after,
        "delta": {k: after[k] - before[k] for k in after},
        "p0_missing_data_cells": mds,
        "extract": {
            "p0_ok": len((extract_report.get("p0") or {}).get("ok") or []),
            "p0_fail": len((extract_report.get("p0") or {}).get("failed") or []),
            "p1_ok": len((extract_report.get("p1") or {}).get("ok") or []),
            "p1_fail": len((extract_report.get("p1") or {}).get("failed") or []),
            "p1_leads": p1_leads,
            "detail": extract_report,
        },
        "status_counts": matrix["status_counts"],
        "coverage": matrix["coverage"],
        "integrity": dup_broken,
        "integrity_runs": integrity_runs,
        "integrity_detail": {
            "p0": extract_report.get("p0_integrity"),
            "p1": extract_report.get("p1_integrity"),
            "p1_harvest": extract_report.get("p1_harvest"),
        },
        "track_validation": track_val,
        "matrix_artifacts": paths,
        "phase5_blocked": True,
        "next_step": (
            "Continue P1 UNRESOLVED harvest/extract for remaining empty city-months "
            "with external proof; keep integrity after each batch; PHASE5 stays blocked "
            "until MISSING_DATA=0 and Coverage/Integrity acceptable."
            if matrix["status_counts"].get("MISSING_DATA", 0) > 0
            or matrix["status_counts"].get("UNRESOLVED", 0) > 0
            else "Coverage obligations cleared — reassess integrity gate for PHASE5."
        ),
    }

    out = ART / "coverage_checkpoint_continue.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    # Final 10-point markdown
    sc = matrix["status_counts"]
    cov = matrix["coverage"]
    tv = track_val["totals"]
    md_lines = [
        "# Coverage Checkpoint Continue — End Report",
        "",
        f"1. Race Day فعلی: **{after['race_days']}** (Δ {report['delta']['race_days']:+d})",
        f"2. Heat فعلی: **{after['heats']}** (Δ {report['delta']['heats']:+d})",
        f"3. Result فعلی: **{after['results']}** (Δ {report['delta']['results']:+d})",
        f"4. MISSING_DATA باقی‌مانده: **{sc.get('MISSING_DATA', 0)}**",
        f"5. UNRESOLVED باقی‌مانده: **{sc.get('UNRESOLVED', 0)}**",
        f"6. Coverage فعلی: **{cov.get('display')}**",
        f"7. Duplicate: **{dup_broken['duplicates']}**",
        f"8. Broken Relations: **{dup_broken['broken_relations']}**",
        f"9. Track Match Coverage: **{tv.get('track_match_coverage_pct')}%** "
        f"({tv.get('matched_heats')}/{tv.get('heats')} heats)",
        f"10. Race بدون Track Configuration: **{tv.get('races_without_track_configuration')}**",
        "",
        "## Track validation (per configured track)",
        "",
        "| Track | Race Days | Heats | Results | Raw name variants |",
        "|---|---:|---:|---:|---|",
    ]
    for t in track_val.get("tracks") or []:
        variants = ", ".join(
            f"{n}×{c}" for n, c in sorted((t.get("raw_name_variants") or {}).items())
        )
        md_lines.append(
            f"| {t['track_name']} ({t['city']}) | {t['total_race_days']} | "
            f"{t['total_heats']} | {t['total_results']} | {variants} |"
        )
    unmatched = track_val.get("unmatched_raw_names") or {}
    if unmatched:
        md_lines += ["", "### Unmatched raw tracks", ""]
        for name, n in unmatched.items():
            md_lines.append(f"- {name}: {n} heats (Track Configuration = UNKNOWN)")

    md_lines += [
        "",
        f"**مرحله بعدی:** {report['next_step']}",
        "",
        "PHASE 5 (Prediction/Ranking/Pedigree/Weather/Betting) همچنان ممنوع است.",
    ]
    md_path = ART / "coverage_checkpoint_continue.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("before", "after", "delta", "status_counts", "coverage", "integrity", "track_validation", "next_step") if k in report}, ensure_ascii=False, indent=2, default=str))
    print(md_path.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
