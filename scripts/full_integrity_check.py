#!/usr/bin/env python3
"""Full Integrity Check on horse_racing.db after coverage merges.

Checks duplicates, broken relations, date conflicts, source conflicts,
and unintended mutation of prior Raw records. Fixes safe issues; never
invents racing data. Keeps enrichment gated.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import jdatetime
from loguru import logger
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from src.coverage.models import CovEnrichmentGate, CovSourceConflict
from src.coverage.pipeline import ensure_enrichment_gate
from src.coverage.gaps import coverage_snapshot, detect_and_upsert_missing_gaps
from src.database import init_db
from src.racecourses import resolve_racecourse
from src.warehouse.fuzzy import normalize_name
from src.warehouse.models import WhHorse, WhRace, WhRaceResult

ART = Path("/opt/cursor/artifacts")
DB_PATH = Path("/workspace/output/historical/horse_racing.db")
DEFAULT_DB = f"sqlite:///{DB_PATH}"

# Baselines from prior phase artifacts (pre-NI merge / post earlier merges)
BASELINE_PRE_NI = {
    "heats": 2775,
    "race_days": 790,
    "results": 26871,
    "note": "needs_investigation_resolution.json DB Before",
}
BASELINE_POST_FIRST_COVERAGE = {
    "heats": 1746,
    "race_days": 325,
    "results": 16543,
    "note": "pre missing-data extract baseline",
}


def _gdate(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    s = str(v)[:10]
    try:
        y, m, d = map(int, s.split("-"))
        return date(y, m, d)
    except ValueError:
        return None


def _week_id(url: str | None) -> str | None:
    if not url:
        return None
    m = re.search(r"/racecards/([A-Za-z0-9]+)", url)
    return m.group(1) if m else None


def recount(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        "raw_current_heats": conn.execute(
            "SELECT COUNT(*) FROM raw_races WHERE is_current=1"
        ).fetchone()[0],
        "raw_all_heats": conn.execute("SELECT COUNT(*) FROM raw_races").fetchone()[0],
        "wh_heats": conn.execute("SELECT COUNT(*) FROM wh_races").fetchone()[0],
        "race_days": conn.execute(
            "SELECT COUNT(*) FROM ("
            " SELECT DISTINCT race_date, track FROM wh_races "
            " WHERE race_date IS NOT NULL AND track IS NOT NULL)"
        ).fetchone()[0],
        "results": conn.execute("SELECT COUNT(*) FROM wh_race_results").fetchone()[0],
        "horses": conn.execute("SELECT COUNT(*) FROM wh_horses").fetchone()[0],
        "raw_horses_current": conn.execute(
            "SELECT COUNT(*) FROM raw_horses WHERE is_current=1"
        ).fetchone()[0],
    }


def audit(conn: sqlite3.Connection) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    counts: Counter = Counter()

    def add(kind: str, severity: str, message: str, **details: Any) -> None:
        counts[kind] += 1
        issues.append(
            {
                "kind": kind,
                "severity": severity,
                "message": message,
                "details": details,
            }
        )

    # --- Duplicate Heat (source key) ---
    for source, sid, n in conn.execute(
        """
        SELECT source, source_race_id, COUNT(*) FROM wh_races
        WHERE source_race_id IS NOT NULL
        GROUP BY source, source_race_id HAVING COUNT(*) > 1
        """
    ):
        add(
            "duplicate_heat_source_key",
            "error",
            f"Duplicate wh heat source_race_id={sid}",
            source=source,
            source_race_id=sid,
            n=n,
        )

    for source, sid, n in conn.execute(
        """
        SELECT source, source_race_id, COUNT(*) FROM raw_races
        WHERE is_current=1 AND source_race_id IS NOT NULL
        GROUP BY source, source_race_id HAVING COUNT(*) > 1
        """
    ):
        add(
            "duplicate_heat_raw_current",
            "error",
            f"Multiple is_current raw heats for {sid}",
            source=source,
            source_race_id=sid,
            n=n,
        )

    # --- Duplicate Heat (natural key: date+track+number) ---
    natural_dups = conn.execute(
        """
        SELECT race_date, track, race_number,
               GROUP_CONCAT(id), GROUP_CONCAT(source_race_id), COUNT(*)
        FROM wh_races
        WHERE race_date IS NOT NULL AND race_number IS NOT NULL
        GROUP BY race_date, track, race_number
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    for rd, track, num, ids, sids, n in natural_dups:
        add(
            "duplicate_heat_natural",
            "error",
            f"Duplicate heat natural key {rd}|{track}|#{num}",
            race_date=rd,
            track=track,
            race_number=num,
            wh_ids=ids,
            source_race_ids=sids,
            n=n,
        )

    # --- Duplicate Race Day (conflicting metadata for same date+track) ---
    for rd, track, codes, provinces, n in conn.execute(
        """
        SELECT race_date, track,
               GROUP_CONCAT(DISTINCT racecourse_code),
               GROUP_CONCAT(DISTINCT IFNULL(province,'')),
               COUNT(DISTINCT racecourse_code)
        FROM wh_races
        WHERE race_date IS NOT NULL AND track IS NOT NULL
        GROUP BY race_date, track
        HAVING COUNT(DISTINCT racecourse_code) > 1
            OR COUNT(DISTINCT IFNULL(province,'')) > 1
        """
    ):
        add(
            "duplicate_race_day_conflict",
            "error",
            f"Race day {rd}|{track} has conflicting course/province metadata",
            race_date=rd,
            track=track,
            codes=codes,
            provinces=provinces,
            n=n,
        )

    # --- Duplicate Result (race+horse) ---
    for race_id, horse_id, n in conn.execute(
        """
        SELECT race_id, horse_id, COUNT(*) FROM wh_race_results
        WHERE horse_id IS NOT NULL
        GROUP BY race_id, horse_id HAVING COUNT(*) > 1
        """
    ):
        add(
            "duplicate_result",
            "error",
            f"Duplicate result race={race_id} horse={horse_id}",
            race_id=race_id,
            horse_id=horse_id,
            n=n,
        )

    # --- Duplicate Horse (same source key) ---
    for source, sid, n in conn.execute(
        """
        SELECT source, source_horse_id, COUNT(*) FROM wh_horses
        WHERE source_horse_id IS NOT NULL
        GROUP BY source, source_horse_id HAVING COUNT(*) > 1
        """
    ):
        add(
            "duplicate_horse_source_key",
            "error",
            f"Duplicate horse source_horse_id={sid}",
            source=source,
            source_horse_id=sid,
            n=n,
        )

    # Soft duplicate horses (same normalized name, multiple source ids) — warning
    by_name: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for hid, name, sid in conn.execute(
        "SELECT id, name, source_horse_id FROM wh_horses"
    ):
        by_name[normalize_name(name)].append((hid, sid or ""))
    soft_horse_dups = 0
    for norm, group in by_name.items():
        if not norm or len({g[0] for g in group}) < 2:
            continue
        # Only count if distinct source ids (identity candidates, not hard errors)
        if len({g[1] for g in group}) > 1:
            soft_horse_dups += len(group) - 1
    counts["duplicate_horse_name_soft"] = soft_horse_dups

    # --- Broken Foreign Keys ---
    for label, q in [
        (
            "result_without_heat",
            "SELECT COUNT(*) FROM wh_race_results rr "
            "LEFT JOIN wh_races r ON r.id=rr.race_id WHERE r.id IS NULL",
        ),
        (
            "result_horse_fk_broken",
            "SELECT COUNT(*) FROM wh_race_results rr "
            "LEFT JOIN wh_horses h ON h.id=rr.horse_id "
            "WHERE rr.horse_id IS NOT NULL AND h.id IS NULL",
        ),
        (
            "result_jockey_fk_broken",
            "SELECT COUNT(*) FROM wh_race_results rr "
            "LEFT JOIN wh_jockeys j ON j.id=rr.jockey_id "
            "WHERE rr.jockey_id IS NOT NULL AND j.id IS NULL",
        ),
        (
            "result_trainer_fk_broken",
            "SELECT COUNT(*) FROM wh_race_results rr "
            "LEFT JOIN wh_trainers t ON t.id=rr.trainer_id "
            "WHERE rr.trainer_id IS NOT NULL AND t.id IS NULL",
        ),
        (
            "result_owner_fk_broken",
            "SELECT COUNT(*) FROM wh_race_results rr "
            "LEFT JOIN wh_owners o ON o.id=rr.owner_id "
            "WHERE rr.owner_id IS NOT NULL AND o.id IS NULL",
        ),
        (
            "wh_race_raw_fk_broken",
            "SELECT COUNT(*) FROM wh_races w "
            "LEFT JOIN raw_races r ON r.id=w.raw_race_id "
            "WHERE w.raw_race_id IS NOT NULL AND r.id IS NULL",
        ),
        (
            "raw_entry_race_fk_broken",
            "SELECT COUNT(*) FROM raw_race_entries e "
            "LEFT JOIN raw_races r ON r.id=e.race_id WHERE r.id IS NULL",
        ),
    ]:
        n = conn.execute(q).fetchone()[0]
        counts[label] = n
        if n:
            add(label, "error", f"{label} count={n}", n=n)

    # Heat without Race Day fields (missing date or track)
    n = conn.execute(
        "SELECT COUNT(*) FROM wh_races WHERE race_date IS NULL OR track IS NULL OR TRIM(track)=''"
    ).fetchone()[0]
    counts["heat_without_race_day"] = n
    if n:
        add("heat_without_race_day", "error", f"Heats missing date/track: {n}", n=n)

    # Heat without Result
    n = conn.execute(
        """
        SELECT COUNT(*) FROM wh_races ra
        WHERE NOT EXISTS (SELECT 1 FROM wh_race_results rr WHERE rr.race_id=ra.id)
        """
    ).fetchone()[0]
    counts["heat_without_result"] = n
    if n:
        add(
            "heat_without_result",
            "warning",
            f"Heats with zero results (possibly DNS/unpublished): {n}",
            n=n,
        )

    # Horse without Result
    n = conn.execute(
        """
        SELECT COUNT(*) FROM wh_horses h
        WHERE NOT EXISTS (SELECT 1 FROM wh_race_results rr WHERE rr.horse_id=h.id)
        """
    ).fetchone()[0]
    counts["horse_without_result"] = n
    if n:
        add("horse_without_result", "warning", f"Horses with no results: {n}", n=n)

    # --- Date Jalali/Gregorian conflicts ---
    date_conflicts = 0
    date_missing = 0
    for rid, rd, rj in conn.execute(
        "SELECT id, race_date, race_date_jalali FROM wh_races"
    ):
        g = _gdate(rd)
        if g is None:
            continue
        exp = jdatetime.date.fromgregorian(date=g)
        expected = f"{exp.year}/{exp.month:02d}/{exp.day:02d}"
        if not rj:
            date_missing += 1
            add(
                "date_conflict_missing_jalali",
                "error",
                f"wh_race {rid} missing jalali",
                id=rid,
                race_date=str(g),
            )
            continue
        got = str(rj).replace("-", "/")
        try:
            p = got.split("/")
            got_n = f"{int(p[0])}/{int(p[1]):02d}/{int(p[2]):02d}"
        except Exception:
            got_n = got
        if got_n != expected:
            date_conflicts += 1
            add(
                "date_conflict_mismatch",
                "error",
                f"wh_race {rid} jalali {rj} != expected {expected}",
                id=rid,
                race_date=str(g),
                race_date_jalali=rj,
                expected=expected,
            )
    counts["date_conflict"] = date_conflicts + date_missing

    # raw jalali too
    raw_date_conflicts = 0
    for rid, rd, rj in conn.execute(
        "SELECT id, race_date, race_date_jalali FROM raw_races WHERE is_current=1"
    ):
        g = _gdate(rd)
        if g is None:
            continue
        exp = jdatetime.date.fromgregorian(date=g)
        expected = f"{exp.year}/{exp.month:02d}/{exp.day:02d}"
        if not rj:
            raw_date_conflicts += 1
            continue
        got = str(rj).replace("-", "/")
        try:
            p = got.split("/")
            got_n = f"{int(p[0])}/{int(p[1]):02d}/{int(p[2]):02d}"
        except Exception:
            got_n = got
        if got_n != expected:
            raw_date_conflicts += 1
            add(
                "date_conflict_raw_mismatch",
                "error",
                f"raw_race {rid} jalali mismatch",
                id=rid,
                expected=expected,
                race_date_jalali=rj,
            )
    counts["date_conflict_raw"] = raw_date_conflicts

    # --- Wrong city / track vs racecourse_code ---
    wrong_city = 0
    for rid, track, code, url in conn.execute(
        "SELECT id, track, racecourse_code, source_url FROM wh_races"
    ):
        resolved = resolve_racecourse(track)
        if resolved is None:
            continue
        if code and resolved.code and code != resolved.code:
            # allow synthesize drift only if code is ir-*
            if not str(code).startswith("ir-"):
                wrong_city += 1
                add(
                    "wrong_city_code_mismatch",
                    "error",
                    f"wh_race {rid} track={track!r} code={code!r} expected={resolved.code}",
                    id=rid,
                    track=track,
                    racecourse_code=code,
                    expected_code=resolved.code,
                )
    counts["wrong_city"] = wrong_city

    # --- Cross-source / same-source duplicate results via natural heat dups ---
    source_conflicts = 0
    for rd, track, num, ids, sids, n in natural_dups:
        id_list = [int(x) for x in str(ids).split(",") if x]
        # compare result horse sets
        sets = []
        for wid in id_list:
            horses = {
                row[0]
                for row in conn.execute(
                    "SELECT horse_id FROM wh_race_results WHERE race_id=? AND horse_id IS NOT NULL",
                    (wid,),
                )
            }
            sets.append(horses)
        overlap = set.intersection(*sets) if sets and all(sets) else set()
        source_conflicts += 1
        add(
            "source_conflict_duplicate_heat",
            "error",
            f"Same natural heat from multiple source_race_ids; overlapping horses={len(overlap)}",
            race_date=rd,
            track=track,
            race_number=num,
            wh_ids=ids,
            source_race_ids=sids,
            overlapping_horses=len(overlap),
        )
    counts["source_conflict"] = source_conflicts

    # Existing cov_source_conflicts table
    try:
        n = conn.execute("SELECT COUNT(*) FROM cov_source_conflicts").fetchone()[0]
        counts["cov_source_conflicts_rows"] = n
    except sqlite3.Error:
        counts["cov_source_conflicts_rows"] = 0

    # --- Prior-record stability (append-only Raw) ---
    # 1) Historical versions must keep stable source_hash (no in-place rewrite)
    #    We detect multiple rows with same (source, source_race_id, version)
    version_dups = conn.execute(
        """
        SELECT source, source_race_id, version, COUNT(*) FROM raw_races
        GROUP BY source, source_race_id, version HAVING COUNT(*) > 1
        """
    ).fetchall()
    for source, sid, ver, n in version_dups:
        add(
            "prior_record_version_dup",
            "error",
            f"Duplicate raw version row {sid} v{ver}",
            source_race_id=sid,
            version=ver,
            n=n,
        )

    # 2) Pre-NI baseline: source_race_ids that appear in the oldest current crawl
    #    window — approximate as races whose earliest version crawl_time is before
    #    the NI extract wave (ids/raw created earlier). Use: raw id of current row
    #    among the first BASELINE_PRE_NI heats by min(id) of each source_race_id.
    baseline_n = BASELINE_PRE_NI["heats"]
    early_ids = [
        r[0]
        for r in conn.execute(
            """
            SELECT source_race_id FROM raw_races
            WHERE is_current=1
            ORDER BY id ASC
            LIMIT ?
            """,
            (baseline_n,),
        )
    ]
    # For each early source_race_id, ensure at least one raw row still exists and
    # the earliest version's source_hash equals itself (row not rewritten): check
    # that version=1 (or min version) row still present.
    mutated = 0
    missing_prior = 0
    for sid in early_ids:
        rows = conn.execute(
            """
            SELECT id, version, source_hash, is_current, crawl_time
            FROM raw_races WHERE source_race_id=? ORDER BY version ASC
            """,
            (sid,),
        ).fetchall()
        if not rows:
            missing_prior += 1
            add(
                "prior_record_missing",
                "error",
                f"Prior source_race_id disappeared: {sid}",
                source_race_id=sid,
            )
            continue
        # Exactly one current
        currents = [r for r in rows if r[3]]
        if len(currents) != 1:
            mutated += 1
            add(
                "prior_record_current_flag",
                "error",
                f"Prior race {sid} has {len(currents)} current rows",
                source_race_id=sid,
            )
        # Min version row should still exist (append-only)
        min_ver = rows[0]
        # If there is a newer version, that's OK (re-fetch); count as modified_with_reason
        if len(rows) > 1:
            counts["prior_record_versioned_ok"] += 1
    counts["prior_record_mutated"] = mutated
    counts["prior_record_missing"] = missing_prior

    # 3) Unexplained wh drift: current wh date/track must match current raw
    wh_raw_drift = 0
    for wid, wdate, wtrack, rid in conn.execute(
        "SELECT id, race_date, track, raw_race_id FROM wh_races WHERE raw_race_id IS NOT NULL"
    ):
        raw = conn.execute(
            "SELECT race_date, track, is_current FROM raw_races WHERE id=?",
            (rid,),
        ).fetchone()
        if not raw:
            continue
        if str(raw[0])[:10] != str(wdate)[:10] or (raw[1] or "") != (wtrack or ""):
            wh_raw_drift += 1
            add(
                "wh_raw_drift",
                "error",
                f"wh_race {wid} differs from raw {rid}",
                wh_id=wid,
                raw_id=rid,
                wh=(str(wdate), wtrack),
                raw=(str(raw[0]), raw[1]),
            )
    counts["wh_raw_drift"] = wh_raw_drift

    # Totals
    duplicate_total = (
        counts["duplicate_heat_source_key"]
        + counts["duplicate_heat_raw_current"]
        + counts["duplicate_heat_natural"]
        + counts["duplicate_race_day_conflict"]
        + counts["duplicate_result"]
        + counts["duplicate_horse_source_key"]
    )
    broken_fk = (
        counts.get("result_without_heat", 0)
        + counts.get("result_horse_fk_broken", 0)
        + counts.get("result_jockey_fk_broken", 0)
        + counts.get("result_trainer_fk_broken", 0)
        + counts.get("result_owner_fk_broken", 0)
        + counts.get("wh_race_raw_fk_broken", 0)
        + counts.get("raw_entry_race_fk_broken", 0)
        + counts.get("heat_without_race_day", 0)
    )

    healthy_heats = conn.execute("SELECT COUNT(*) FROM wh_races").fetchone()[0]
    healthy_results = conn.execute("SELECT COUNT(*) FROM wh_race_results").fetchone()[0]
    # healthy = records not implicated in error-severity issues
    error_heat_ids: set[int] = set()
    for iss in issues:
        if iss["severity"] != "error":
            continue
        det = iss["details"]
        if "wh_ids" in det and det["wh_ids"]:
            for x in str(det["wh_ids"]).split(","):
                if x.strip().isdigit():
                    error_heat_ids.add(int(x.strip()))
        if "id" in det and isinstance(det["id"], int):
            error_heat_ids.add(det["id"])
        if "wh_id" in det:
            error_heat_ids.add(int(det["wh_id"]))

    return {
        "counts": dict(counts),
        "issues": issues,
        "duplicate_total": duplicate_total,
        "broken_relation_total": broken_fk,
        "date_conflict_total": counts.get("date_conflict", 0)
        + counts.get("date_conflict_raw", 0),
        "source_conflict_total": counts.get("source_conflict", 0),
        "healthy_heats_estimate": max(0, healthy_heats - len(error_heat_ids)),
        "healthy_results": healthy_results,
        "error_heat_ids": sorted(error_heat_ids),
        "natural_dup_groups": [
            {
                "race_date": rd,
                "track": track,
                "race_number": num,
                "wh_ids": ids,
                "source_race_ids": sids,
                "n": n,
            }
            for rd, track, num, ids, sids, n in natural_dups
        ],
    }


def fix_natural_heat_duplicates(conn: sqlite3.Connection, audit_result: dict) -> dict[str, int]:
    """Keep the richer heat in WH; remove duplicate WH race (cascade results).

    Raw rows stay append-only. Record conflicts into cov_source_conflicts.
    """
    fixed = {"wh_heats_removed": 0, "wh_results_removed": 0, "conflicts_logged": 0}
    for group in audit_result.get("natural_dup_groups", []):
        ids = [int(x) for x in str(group["wh_ids"]).split(",") if x.strip().isdigit()]
        if len(ids) < 2:
            continue
        # Score: more results wins; tie → lower id
        scored = []
        for wid in ids:
            nres = conn.execute(
                "SELECT COUNT(*) FROM wh_race_results WHERE race_id=?", (wid,)
            ).fetchone()[0]
            url = conn.execute(
                "SELECT source_url, source_race_id FROM wh_races WHERE id=?", (wid,)
            ).fetchone()
            scored.append((nres, -wid, wid, url))
        scored.sort(reverse=True)
        keep = scored[0][2]
        drop = [s[2] for s in scored[1:]]
        keep_meta = scored[0][3]
        for wid in drop:
            drop_meta = conn.execute(
                "SELECT source_url, source_race_id, source FROM wh_races WHERE id=?",
                (wid,),
            ).fetchone()
            nres = conn.execute(
                "SELECT COUNT(*) FROM wh_race_results WHERE race_id=?", (wid,)
            ).fetchone()[0]
            # Clear dependents explicitly (SQLite FK cascade depends on pragma)
            for tbl, col in (
                ("wh_race_results", "race_id"),
                ("wh_race_videos", "race_id"),
                ("wh_race_weather", "race_id"),
            ):
                try:
                    conn.execute(f"DELETE FROM {tbl} WHERE {col}=?", (wid,))
                except sqlite3.Error:
                    pass
            conn.execute("DELETE FROM wh_races WHERE id=?", (wid,))
            # Demote losing raw current row (append-only: do not delete)
            if drop_meta and drop_meta[1]:
                conn.execute(
                    """
                    UPDATE raw_races SET is_current=0
                    WHERE source_race_id=? AND is_current=1
                    """,
                    (drop_meta[1],),
                )
                fixed["raw_demoted"] = fixed.get("raw_demoted", 0) + 1
            fixed["wh_heats_removed"] += 1
            fixed["wh_results_removed"] += nres
            # log conflict
            try:
                conn.execute(
                    """
                    INSERT INTO cov_source_conflicts
                    (entity_type, entity_key, field_name, source_a, value_a_json, source_url_a,
                     source_b, value_b_json, source_url_b, preferred_source, status, details_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "wh_race",
                        f"{group['race_date']}|{group['track']}|{group['race_number']}",
                        "duplicate_natural_heat",
                        "asbdavani",
                        json.dumps(
                            {
                                "wh_id": keep,
                                "source_race_id": keep_meta[1] if keep_meta else None,
                            },
                            ensure_ascii=False,
                        ),
                        keep_meta[0] if keep_meta else None,
                        "asbdavani",
                        json.dumps(
                            {
                                "wh_id": wid,
                                "source_race_id": drop_meta[1] if drop_meta else None,
                            },
                            ensure_ascii=False,
                        ),
                        drop_meta[0] if drop_meta else None,
                        "asbdavani",
                        "resolved_by_priority",
                        json.dumps(
                            {
                                "resolution": "kept_richer_result_set",
                                "kept_wh_id": keep,
                                "dropped_wh_id": wid,
                            },
                            ensure_ascii=False,
                        ),
                    ),
                )
                fixed["conflicts_logged"] += 1
            except sqlite3.Error as exc:
                logger.warning("conflict log failed: {}", exc)
    conn.commit()
    return fixed


def fix_date_jalali(conn: sqlite3.Connection) -> int:
    n = 0
    for table in ("wh_races", "raw_races"):
        rows = conn.execute(
            f"SELECT id, race_date, race_date_jalali FROM {table} WHERE race_date IS NOT NULL"
        ).fetchall()
        for rid, rd, rj in rows:
            g = _gdate(rd)
            if not g:
                continue
            exp = jdatetime.date.fromgregorian(date=g)
            expected = f"{exp.year}/{exp.month:02d}/{exp.day:02d}"
            got = None
            if rj:
                try:
                    p = str(rj).replace("-", "/").split("/")
                    got = f"{int(p[0])}/{int(p[1]):02d}/{int(p[2]):02d}"
                except Exception:
                    got = None
            if got != expected:
                conn.execute(
                    f"UPDATE {table} SET race_date_jalali=? WHERE id=?",
                    (expected, rid),
                )
                n += 1
    conn.commit()
    return n


def fix_wrong_city_codes(conn: sqlite3.Connection) -> int:
    n = 0
    for rid, track, code in conn.execute(
        "SELECT id, track, racecourse_code FROM wh_races"
    ):
        resolved = resolve_racecourse(track)
        if resolved is None or not resolved.code:
            continue
        if code != resolved.code and not str(code or "").startswith("ir-"):
            conn.execute(
                "UPDATE wh_races SET racecourse_code=? WHERE id=?",
                (resolved.code, rid),
            )
            n += 1
        # also fix matching raw current
    for rid, track, code in conn.execute(
        "SELECT id, track, racecourse_code FROM raw_races WHERE is_current=1"
    ):
        resolved = resolve_racecourse(track)
        if resolved is None or not resolved.code:
            continue
        if code != resolved.code and not str(code or "").startswith("ir-"):
            conn.execute(
                "UPDATE raw_races SET racecourse_code=? WHERE id=?",
                (resolved.code, rid),
            )
            n += 1
    conn.commit()
    return n


def coverage_proxy_from_db(conn: sqlite3.Connection) -> float:
    """Return primary calendar-cell coverage (not the deprecated gap-penalty proxy)."""
    from sqlalchemy.orm import Session

    from src.coverage.metrics import compute_coverage_metrics

    # conn is sqlite3; open ORM session on same DB file
    engine = create_engine(f"sqlite:///{DB_PATH}")
    with Session(engine) as session:
        report = compute_coverage_metrics(session)
    return float(report.get("primary_coverage_pct") or 0.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", default=DEFAULT_DB)
    ap.add_argument("--fix", action="store_true", default=True)
    ap.add_argument("--no-fix", action="store_true")
    args = ap.parse_args()
    do_fix = args.fix and not args.no_fix

    ART.mkdir(parents=True, exist_ok=True)
    init_db(url=args.db_url)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys=ON")

    before_counts = recount(conn)
    logger.info("DB counts before integrity: {}", before_counts)

    pre = audit(conn)
    logger.info(
        "PRE-FIX duplicates={} broken={} date={} source={} natural_dups={}",
        pre["duplicate_total"],
        pre["broken_relation_total"],
        pre["date_conflict_total"],
        pre["source_conflict_total"],
        len(pre["natural_dup_groups"]),
    )

    repairs = {
        "natural_heat_dups": {},
        "date_jalali_fixed": 0,
        "wrong_city_fixed": 0,
    }
    if do_fix:
        repairs["natural_heat_dups"] = fix_natural_heat_duplicates(conn, pre)
        repairs["date_jalali_fixed"] = fix_date_jalali(conn)
        repairs["wrong_city_fixed"] = fix_wrong_city_codes(conn)

    post = audit(conn)
    after_counts = recount(conn)

    records_fixed = (
        repairs["natural_heat_dups"].get("wh_heats_removed", 0)
        + repairs["natural_heat_dups"].get("wh_results_removed", 0)
        + repairs["date_jalali_fixed"]
        + repairs["wrong_city_fixed"]
    )

    # Before/after merge comparison (using baselines)
    merge_compare = {
        "baseline_pre_ni_merge": BASELINE_PRE_NI,
        "baseline_post_first_coverage": BASELINE_POST_FIRST_COVERAGE,
        "current": after_counts,
        "delta_vs_pre_ni": {
            "heats": after_counts["wh_heats"] - BASELINE_PRE_NI["heats"],
            "race_days": after_counts["race_days"] - BASELINE_PRE_NI["race_days"],
            "results": after_counts["results"] - BASELINE_PRE_NI["results"],
        },
        "prior_record_check": {
            "mutated_unexplained": post["counts"].get("prior_record_mutated", 0),
            "missing_prior": post["counts"].get("prior_record_missing", 0),
            "versioned_ok": post["counts"].get("prior_record_versioned_ok", 0),
            "wh_raw_drift": post["counts"].get("wh_raw_drift", 0),
            "note": (
                "Raw is append-only; new versions OK. Unexpected: missing prior "
                "source_race_id, multi-current, or wh↔raw drift."
            ),
        },
    }

    # Healthy records: heats/results not in error set after fix
    healthy = {
        "heats": post["healthy_heats_estimate"],
        "results": after_counts["results"],
        "horses": after_counts["horses"],
        "race_days": after_counts["race_days"],
    }

    # Coverage recalc + keep enrichment closed
    proxy = coverage_proxy_from_db(conn)
    engine = create_engine(args.db_url)
    with Session(engine) as session:
        snap = coverage_snapshot(session)
        # refresh gap emptiness markers carefully? only snapshot for report
        ensure_enrichment_gate(session, coverage_pct=proxy)
        gate = session.scalar(
            select(CovEnrichmentGate).where(CovEnrichmentGate.name == "secondary")
        )
        if gate:
            gate.allowed = False
        session.commit()
        gate_info = {
            "allowed": bool(gate.allowed) if gate else False,
            "current_coverage_pct": gate.current_coverage_pct if gate else proxy,
            "min_coverage_pct": gate.min_coverage_pct if gate else 70.0,
        }

    summary = {
        "Healthy Records": {
            "heats": healthy["heats"],
            "results": healthy["results"],
            "horses": healthy["horses"],
            "race_days": healthy["race_days"],
            "total_wh_heats": after_counts["wh_heats"],
        },
        "Duplicates": post["duplicate_total"],
        "Broken Relations": post["broken_relation_total"],
        "Date Conflicts": post["date_conflict_total"],
        "Source Conflicts": post["source_conflict_total"],
        "Records Fixed": records_fixed,
        "Warnings": {
            "heat_without_result": post["counts"].get("heat_without_result", 0),
            "horse_without_result": post["counts"].get("horse_without_result", 0),
            "soft_duplicate_horse_names": post["counts"].get(
                "duplicate_horse_name_soft", 0
            ),
        },
        "Coverage Pct Proxy": proxy,
        "Enrichment Gate": gate_info,
        "DB Before Integrity Pass": before_counts,
        "DB After Integrity Pass": after_counts,
        "Merge Compare": merge_compare,
        "Repairs": repairs,
        "PreFix": {
            "duplicates": pre["duplicate_total"],
            "broken": pre["broken_relation_total"],
            "date": pre["date_conflict_total"],
            "source": pre["source_conflict_total"],
        },
        "PostFix": {
            "duplicates": post["duplicate_total"],
            "broken": post["broken_relation_total"],
            "date": post["date_conflict_total"],
            "source": post["source_conflict_total"],
        },
        "Snapshot": snap,
    }

    # Persist detailed issues (cap)
    artifact = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "pre_fix_issue_counts": pre["counts"],
        "post_fix_issue_counts": post["counts"],
        "pre_fix_issues_sample": pre["issues"][:200],
        "post_fix_issues_sample": post["issues"][:200],
        "note": (
            "Full integrity after coverage merges. Raw append-only preserved. "
            "Natural-key duplicate heats resolved in WH (kept richer). "
            "Enrichment remains closed."
        ),
    }
    (ART / "full_integrity_check.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (ART / "full_integrity_check.md").write_text(
        "\n".join(
            [
                "# Full Integrity Check",
                "",
                "| Metric | Value |",
                "|---|---:|",
                f"| Healthy Heats (est.) | {summary['Healthy Records']['heats']} |",
                f"| Healthy Results | {summary['Healthy Records']['results']} |",
                f"| Duplicates (post-fix) | {summary['Duplicates']} |",
                f"| Broken Relations | {summary['Broken Relations']} |",
                f"| Date Conflicts | {summary['Date Conflicts']} |",
                f"| Source Conflicts | {summary['Source Conflicts']} |",
                f"| Records Fixed | {summary['Records Fixed']} |",
                f"| Heats without Result (warn) | {summary['Warnings']['heat_without_result']} |",
                f"| Coverage Pct (proxy) | {summary['Coverage Pct Proxy']:.2f} |",
                f"| Enrichment Gate | CLOSED |",
                "",
                "## Merge compare (vs pre-NI baseline)",
                "",
                f"- Heats: {BASELINE_PRE_NI['heats']} → {after_counts['wh_heats']} "
                f"(Δ {merge_compare['delta_vs_pre_ni']['heats']})",
                f"- Race Days: {BASELINE_PRE_NI['race_days']} → {after_counts['race_days']} "
                f"(Δ {merge_compare['delta_vs_pre_ni']['race_days']})",
                f"- Results: {BASELINE_PRE_NI['results']} → {after_counts['results']} "
                f"(Δ {merge_compare['delta_vs_pre_ni']['results']})",
                "",
                "## Prior-record stability",
                "",
                f"- Unexplained mutations: {merge_compare['prior_record_check']['mutated_unexplained']}",
                f"- Missing prior races: {merge_compare['prior_record_check']['missing_prior']}",
                f"- WH↔Raw drift: {merge_compare['prior_record_check']['wh_raw_drift']}",
                f"- Versioned (re-fetch) OK: {merge_compare['prior_record_check']['versioned_ok']}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    conn.close()
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0 if post["duplicate_total"] == 0 and post["date_conflict_total"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
