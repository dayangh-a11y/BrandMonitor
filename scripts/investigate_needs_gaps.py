#!/usr/bin/env python3
"""Investigate Needs Investigation gaps → No-Race / Missing-Data / Unresolved.

Never invent data. Enrichment stays gated.
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
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from src.asbdavani.constants import absolute_url
from src.collectors.race_collector import RaceCollector
from src.coverage.models import CovEnrichmentGate, CovMissingGap
from src.coverage.pipeline import ensure_enrichment_gate
from src.database import init_db
from src.datasources import get_datasource
from src.identity import build_horse_identity
from src.utils.jalali import today_jalali
from src.warehouse import build_warehouse, run_entity_resolution
from src.warehouse.models import WhRace

ART = Path("/opt/cursor/artifacts")
DB_PATH = Path("/workspace/output/historical/horse_racing.db")
DEFAULT_DB = f"sqlite:///{DB_PATH}"
HISTORY_PATH = Path("/tmp/history_evidence_ni.json")
PRIOR_HISTORY = Path("/tmp/history_evidence.json")

TRACK_ALIASES = {
    "آققلا": "آق قلا",
    "آق قلا": "آق قلا",
    "گنبد": "گنبدکاووس",
    "گنبد کاووس": "گنبدکاووس",
    "گنبدکاووس": "گنبدکاووس",
    "بندر ترکمن": "بندرترکمن",
    "بندرترکمن": "بندرترکمن",
    "انبارالوم": "انبارآلوم",
    "انبار آلوم": "انبارآلوم",
    "انبارآلوم": "انبارآلوم",
    "تهران": "تهران",
    "یزد": "یزد",
    "اهواز": "اهواز",
    "کیش": "کیش",
    "مشهد": "مشهد",
}


def norm_track(s: str | None) -> str | None:
    if not s:
        return None
    t = str(s).replace("\u200c", "").replace("\u200d", "")
    t = re.sub(r"\s+", " ", t).strip()
    return TRACK_ALIASES.get(t, t)


def stratified_profiles(limit: int = 1200) -> list[str]:
    """Prefer horses that already raced at NI-heavy / sparse tracks."""
    conn = sqlite3.connect(str(DB_PATH))
    targets = [
        "مشهد",
        "انبارآلوم",
        "کیش",
        "اهواز",
        "آق قلا",
        "یزد",
        "تهران",
        "بندرترکمن",
        "گنبدکاووس",
    ]
    q = f"""
    SELECT h.profile_url, r.track, COUNT(*) AS n
    FROM wh_race_results rr
    JOIN wh_races r ON r.id = rr.race_id
    JOIN wh_horses h ON h.id = rr.horse_id
    WHERE h.profile_url IS NOT NULL AND TRIM(h.profile_url) != ''
      AND r.track IN ({",".join("?" * len(targets))})
    GROUP BY h.profile_url, r.track
    ORDER BY
      CASE r.track
        WHEN 'مشهد' THEN 0 WHEN 'انبارآلوم' THEN 1 WHEN 'کیش' THEN 2
        WHEN 'اهواز' THEN 3 WHEN 'آق قلا' THEN 4 ELSE 5 END,
      n DESC
    """
    rows = conn.execute(q, targets).fetchall()
    # also oldest horses (low id) for deep archive
    old = conn.execute(
        """
        SELECT profile_url FROM wh_horses
        WHERE profile_url IS NOT NULL AND TRIM(profile_url) != ''
        ORDER BY id ASC LIMIT 800
        """
    ).fetchall()
    conn.close()

    seen: set[str] = set()
    out: list[str] = []
    # prioritize sparse-track horses first
    sparse_order = ["مشهد", "انبارآلوم", "کیش", "اهواز"]
    by_track: dict[str, list[str]] = defaultdict(list)
    for url, track, _n in rows:
        by_track[track].append(url)
    for t in sparse_order:
        for u in by_track.get(t, []):
            if u not in seen:
                seen.add(u)
                out.append(u)
            if len(out) >= limit // 2:
                break
        if len(out) >= limit // 2:
            break
    for url, _track, _n in rows:
        if url not in seen:
            seen.add(url)
            out.append(url)
        if len(out) >= limit:
            break
    for (u,) in old:
        if u not in seen:
            seen.add(u)
            out.append(u)
        if len(out) >= limit:
            break
    return out[:limit]


def harvest_histories(profiles: list[str], *, sleep_s: float = 0.28) -> dict[str, Any]:
    ds = get_datasource("asbdavani")
    cells: dict[str, list] = defaultdict(list)
    ok = err = 0
    try:
        for i, purl in enumerate(profiles, 1):
            try:
                hist = ds.collect_horse_history(purl)
                ok += 1
            except Exception as exc:  # noqa: BLE001
                err += 1
                logger.warning("history fail {}: {}", purl, exc)
                time.sleep(sleep_s)
                continue
            horse = getattr(hist, "horse_name", None) or getattr(hist, "name", None)
            for row in hist.history:
                url = getattr(row, "race_url", None) or getattr(row, "raceUrl", None)
                d = getattr(row, "race_date", None) or getattr(row, "date", None)
                track = getattr(row, "track", None) or getattr(row, "racecourse", None)
                rnd = getattr(row, "race_number", None) or getattr(row, "round", None)
                finish = getattr(row, "finish_position", None) or getattr(row, "position", None)
                if not d:
                    continue
                if hasattr(d, "isoformat"):
                    g = d if isinstance(d, date) else date.fromisoformat(str(d)[:10])
                    ds_ = g.isoformat()
                    jd = jdatetime.date.fromgregorian(date=g)
                else:
                    ds_ = str(d)[:10]
                    try:
                        jd = jdatetime.date.fromgregorian(date=date.fromisoformat(ds_))
                    except ValueError:
                        continue
                u = absolute_url(str(url)).split("#")[0] if url else None
                item = {
                    "date": ds_,
                    "date_j": f"{jd.year}/{jd.month:02d}/{jd.day:02d}",
                    "track": track,
                    "url": u,
                    "horse": horse,
                    "round": rnd,
                    "finish": finish,
                    "horse_id": purl,
                    "source": "asbdavani_horse_history",
                }
                unknown = "?"
                cells[f"{jd.year}|{jd.month}|{track or unknown}"].append(item)
                cells[f"{jd.year}|{jd.month}|*"].append(item)
            if i % 25 == 0:
                logger.info("harvest {}/{} ok={} err={} cells={}", i, len(profiles), ok, err, len(cells))
                _save_partial(cells, ok, err, len(profiles))
            time.sleep(sleep_s)
    finally:
        close = getattr(ds, "close", None)
        if callable(close):
            close()
    return {"ok": ok, "errors": err, "cells": dict(cells)}


def _save_partial(cells, ok, err, targeted) -> None:
    HISTORY_PATH.write_text(
        json.dumps(
            {
                "profiles_targeted": targeted,
                "profiles_scanned_ok": ok,
                "errors": err,
                "cells": {k: v for k, v in cells.items()},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def merge_history_sources(*paths: Path) -> dict[str, list]:
    merged: dict[str, list] = defaultdict(list)
    for p in paths:
        if not p.exists():
            continue
        payload = json.loads(p.read_text(encoding="utf-8"))
        for k, rows in payload.get("cells", {}).items():
            merged[k].extend(rows)
    final: dict[str, list] = {}
    for k, rows in merged.items():
        seen: set[tuple] = set()
        uniq = []
        for r in rows:
            sig = (r.get("url"), r.get("horse"), r.get("date"), r.get("round"))
            if sig in seen:
                continue
            seen.add(sig)
            uniq.append(r)
        final[k] = uniq
    return final


def index_history(cells: dict[str, list]) -> tuple[dict, dict]:
    hist_city: dict[tuple[int, int, str], list] = defaultdict(list)
    hist_month: dict[tuple[int, int], list] = defaultdict(list)
    for key, rows in cells.items():
        parts = key.split("|")
        if len(parts) != 3:
            continue
        y, m, city = int(parts[0]), int(parts[1]), parts[2]
        city_n = None if city == "*" else norm_track(city)
        if city_n is None:
            hist_month[(y, m)].extend(rows)
        else:
            hist_city[(y, m, city_n)].extend(rows)
            hist_month[(y, m)].extend(rows)
    return hist_city, hist_month


def summarize(rows: list[dict]) -> dict[str, Any]:
    dates = sorted({r.get("date") for r in rows if r.get("date")})
    urls = sorted({(r.get("url") or "").split("#")[0] for r in rows if r.get("url")})
    horses = sorted({r.get("horse") for r in rows if r.get("horse")})
    tracks = sorted({norm_track(r.get("track")) for r in rows if r.get("track")})
    return {
        "race_days": len(dates),
        "heats": len(urls),
        "results": len(rows),
        "dates": dates,
        "urls": urls,
        "sample_horses": horses[:12],
        "cities": [t for t in tracks if t],
    }


def classify_one(
    *,
    scope_type: str,
    year: int,
    month: int,
    track: str | None,
    hist_city,
    hist_month,
    jy_today: int,
    jm_today: int,
    sources_checked: list[str],
) -> dict[str, Any]:
    city = norm_track(track)

    # 1) Future calendar → Confirmed No-Race
    if (year > jy_today) or (year == jy_today and month > jm_today):
        return {
            "result": "confirmed_no_race",
            "source_checked": "calendar_asia_tehran",
            "source_url": None,
            "evidence": {
                "rule": "future_jalali_month",
                "today_jalali": f"{jy_today}/{jm_today:02d}",
                "cell": f"{year}/{month:02d}",
            },
            "confidence": 0.99,
            "race_days": 0,
            "heats": 0,
            "results": 0,
            "urls": [],
            "sources_checked": sources_checked + ["calendar_asia_tehran"],
        }

    rows: list[dict] = []
    if scope_type == "month":
        rows = list(hist_month.get((year, month), []))
    elif city:
        rows = list(hist_city.get((year, month, city), []))

    if rows:
        summ = summarize(rows)
        # Require at least one concrete date (+ preferably URL). Date+track from
        # official asbdavani career pages is positive proof of racing.
        conf = 0.92 if summ["urls"] else 0.78
        return {
            "result": "confirmed_missing_data",
            "source_checked": "asbdavani_horse_history",
            "source_url": summ["urls"][0] if summ["urls"] else "https://asbdavani.app/",
            "evidence": {
                "proving": "horse career history lists official race starts in this cell",
                "dates": summ["dates"],
                "cities": summ["cities"],
                "sample_horses": summ["sample_horses"],
                "url_count": len(summ["urls"]),
            },
            "confidence": conf,
            "race_days": summ["race_days"],
            "heats": summ["heats"],
            "results": summ["results"],
            "urls": summ["urls"],
            "sources_checked": sources_checked + ["asbdavani_horse_history"],
        }

    # No positive proof of racing or absence → Unresolved (never invent No-Race)
    return {
        "result": "unresolved",
        "source_checked": ",".join(sources_checked),
        "source_url": None,
        "evidence": {
            "note": (
                "Checked asbdavani horse-history sample and calendar-future rule; "
                "no positive proof of official races in this cell, and no citable "
                "federation calendar proving absence"
            ),
            "suggested_next": [
                "federation_calendar_pdf",
                "provincial_notices",
                "deeper_horse_history",
                "asbdavani_week_archive_beyond_public_index",
            ],
        },
        "confidence": 0.35,
        "race_days": 0,
        "heats": 0,
        "results": 0,
        "urls": [],
        "sources_checked": sources_checked,
    }


def existing_urls() -> set[str]:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        return {
            (u or "").split("#")[0]
            for (u,) in conn.execute(
                "SELECT source_url FROM raw_races WHERE source_url IS NOT NULL"
            )
        }
    finally:
        conn.close()


def recount() -> dict[str, int]:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        return {
            "heats": conn.execute(
                "SELECT COUNT(*) FROM raw_races WHERE is_current=1"
            ).fetchone()[0],
            "wh_heats": conn.execute("SELECT COUNT(*) FROM wh_races").fetchone()[0],
            "race_days": conn.execute(
                "SELECT COUNT(*) FROM (SELECT DISTINCT race_date, track FROM wh_races "
                "WHERE race_date IS NOT NULL AND track IS NOT NULL)"
            ).fetchone()[0],
            "results": conn.execute("SELECT COUNT(*) FROM wh_race_results").fetchone()[0],
        }
    finally:
        conn.close()


def extract_urls(urls: list[str], *, sleep_s: float = 0.35) -> dict[str, Any]:
    out_dir = Path("output/historical/coverage/ni_missing_data_extract")
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
                fail.append({"url": url, "error": str(exc)[:300]})
                logger.error("extract fail {}: {}", url, exc)
            if i % 25 == 0:
                logger.info("extract {}/{} ok={} fail={}", i, len(urls), len(ok), len(fail))
            time.sleep(sleep_s)
    finally:
        close = getattr(getattr(collector, "datasource", None), "close", None)
        if callable(close):
            close()
    return {"new": len(ok), "failed": fail, "ok": ok}


def coverage_proxy(remaining_problem: int) -> float:
    """Deprecated arg ignored; returns primary calendar-cell coverage."""
    from src.coverage.metrics import compute_coverage_metrics
    from src.database import session_scope

    with session_scope() as session:
        return float(compute_coverage_metrics(session).get("primary_coverage_pct") or 0.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", default=DEFAULT_DB)
    ap.add_argument("--harvest", type=int, default=0, help="Harvest N stratified horse histories")
    ap.add_argument("--extract", action="store_true")
    ap.add_argument("--max-extract", type=int, default=1500)
    ap.add_argument("--classify-only", action="store_true")
    args = ap.parse_args()

    os.environ.setdefault("CRAWL_ALLOWED_RACECOURSES", "*")
    os.environ.setdefault("DATABASE_URL", args.db_url)
    ART.mkdir(parents=True, exist_ok=True)
    init_db(url=args.db_url)
    engine = create_engine(args.db_url)

    today = today_jalali()
    jy_today, jm_today = today.year, today.month
    before = recount()
    logger.info("before {}", before)

    if args.harvest > 0 and not args.classify_only:
        profiles = stratified_profiles(args.harvest)
        logger.info("harvesting {} stratified profiles", len(profiles))
        harvested = harvest_histories(profiles)
        HISTORY_PATH.write_text(
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
        logger.info("harvest done ok={} err={}", harvested["ok"], harvested["errors"])

    merged_cells = merge_history_sources(PRIOR_HISTORY, HISTORY_PATH)
    hist_city, hist_month = index_history(merged_cells)
    logger.info(
        "evidence cells city={} month_keys={} row_total={}",
        len(hist_city),
        len(hist_month),
        sum(len(v) for v in merged_cells.values()),
    )

    sources_base = [
        "asbdavani_horse_history",
        "asbdavani_racecards_index_182",
        "mosharekat_race_days",
        "calendar_asia_tehran",
    ]

    classified: list[dict[str, Any]] = []
    with Session(engine) as session:
        gaps = session.scalars(
            select(CovMissingGap).where(
                CovMissingGap.status.in_(["needs_investigation", "unresolved"])
            )
        ).all()
        logger.info("investigating {} gaps", len(gaps))
        for g in gaps:
            y, m = int(g.jalali_year or 0), int(g.jalali_month or 0)
            result = classify_one(
                scope_type=g.scope_type,
                year=y,
                month=m,
                track=g.track,
                hist_city=hist_city,
                hist_month=hist_month,
                jy_today=jy_today,
                jm_today=jm_today,
                sources_checked=list(sources_base),
            )
            row = {
                "id": g.id,
                "jalali_year": y,
                "jalali_month": m,
                "city": g.track,
                "scope_type": g.scope_type,
                **result,
            }
            classified.append(row)

            prev = g.evidence_json if isinstance(g.evidence_json, dict) else {}
            g.evidence_json = {
                **prev,
                "ni_phase": {
                    "result": result["result"],
                    "source_checked": result["source_checked"],
                    "source_url": result["source_url"],
                    "evidence": result["evidence"],
                    "confidence": result["confidence"],
                    "race_days": result["race_days"],
                    "heats": result["heats"],
                    "results": result["results"],
                    "urls": result["urls"][:15],
                    "sources_checked": result["sources_checked"],
                    "at_utc": datetime.now(timezone.utc).isoformat(),
                },
            }
            if result["result"] == "confirmed_no_race":
                g.status = "confirmed_no_race"
                g.notes = "NI-phase: future month"
            elif result["result"] == "confirmed_missing_data":
                g.status = "confirmed_missing_data"
                g.notes = (
                    f"NI-phase missing data conf={result['confidence']}; "
                    f"days={result['race_days']} heats={result['heats']}"
                )
            else:
                g.status = "unresolved"
                g.notes = "NI-phase: unresolved — insufficient evidence"
            g.updated_at = datetime.now(timezone.utc)
        session.commit()

    counts = Counter(r["result"] for r in classified)
    logger.info("classification {}", dict(counts))

    extract_stats: dict[str, Any] = {"attempted": 0, "new": 0, "failed": []}
    merge_stats: dict[str, Any] = {}
    missing = [r for r in classified if r["result"] == "confirmed_missing_data"]
    url_set = {
        u.split("#")[0]
        for r in missing
        for u in r["urls"]
        if u and "/racecards/" in u
    }
    already = existing_urls()
    to_extract = sorted(u for u in url_set if u not in already)[: args.max_extract]
    logger.info("extract candidates {} (already {})", len(to_extract), len(url_set) - len(to_extract))

    if args.extract and not args.classify_only and to_extract:
        extract_stats["attempted"] = len(to_extract)
        Path("/tmp/ni_extract_urls.json").write_text(
            json.dumps(to_extract, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        out = extract_urls(to_extract)
        extract_stats["new"] = out["new"]
        extract_stats["failed"] = out["failed"][:40]
        extract_stats["failed_count"] = len(out["failed"])

        with Session(engine) as session:
            wh = build_warehouse(session)
            er = run_entity_resolution(session)
            ident = build_horse_identity(session)
            merge_stats = {"warehouse": wh, "entity_resolution": er, "identity": ident}

            races = session.scalars(select(WhRace).where(WhRace.race_date.is_not(None))).all()
            by_ym: dict[tuple[int, int], int] = defaultdict(int)
            by_ym_track: dict[tuple[int, int, str], int] = defaultdict(int)
            for r in races:
                jd = jdatetime.date.fromgregorian(date=r.race_date)
                by_ym[(jd.year, jd.month)] += 1
                if r.track:
                    by_ym_track[(jd.year, jd.month, r.track)] += 1

            filled = 0
            for g in session.scalars(
                select(CovMissingGap).where(CovMissingGap.status == "confirmed_missing_data")
            ).all():
                y, m = g.jalali_year, g.jalali_month
                if y is None or m is None:
                    continue
                if g.scope_type == "month" and by_ym.get((y, m), 0) > 0:
                    g.status = "resolved_filled"
                    filled += 1
                elif g.scope_type == "city_month" and g.track:
                    if by_ym_track.get((y, m, g.track), 0) > 0:
                        g.status = "resolved_filled"
                        filled += 1
            extract_stats["cells_resolved_filled"] = filled
            session.commit()

    after = recount()

    with Session(engine) as session:
        status_rows = dict(
            session.execute(
                select(CovMissingGap.status, func.count()).group_by(CovMissingGap.status)
            ).all()
        )
        unresolved_n = int(status_rows.get("unresolved", 0) + status_rows.get("needs_investigation", 0))
        still_md = int(status_rows.get("confirmed_missing_data", 0))
        rem = unresolved_n + still_md
        proxy = coverage_proxy(rem)
        ensure_enrichment_gate(session, coverage_pct=proxy)
        gate = session.scalar(
            select(CovEnrichmentGate).where(CovEnrichmentGate.name == "secondary")
        )
        if gate:
            gate.allowed = False
        session.commit()

    # Phase metrics relative to the 1328 NI set
    summary = {
        "Phase": "Needs Investigation resolution",
        "Input Needs Investigation": len(classified),
        "Confirmed No-Race": counts.get("confirmed_no_race", 0),
        "Confirmed Missing Data": counts.get("confirmed_missing_data", 0),
        "Unresolved": counts.get("unresolved", 0),
        "New Race Days": max(0, after["race_days"] - before["race_days"]),
        "New Heats": max(0, after["wh_heats"] - before["wh_heats"]),
        "New Results": max(0, after["results"] - before["results"]),
        "Coverage Pct Proxy": proxy,
        "Enrichment Gate Allowed": False,
        "DB Before": before,
        "DB After": after,
        "Status Counts": {str(k): int(v) for k, v in status_rows.items()},
        "Extract": {
            "attempted": extract_stats.get("attempted", 0),
            "new": extract_stats.get("new", 0),
            "failed_count": extract_stats.get("failed_count", 0),
            "cells_resolved_filled": extract_stats.get("cells_resolved_filled", 0),
        },
        "Evidence History Cells": len(merged_cells),
        "Today Jalali": f"{jy_today}/{jm_today:02d}/{today.day:02d}",
    }

    artifact = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "merge": merge_stats,
        "extract_failures": extract_stats.get("failed", []),
        "cells": classified,
        "note": (
            "Needs Investigation cells reclassified with evidence only. "
            "No-Race only for future Jalali months. Missing Data only with "
            "asbdavani horse-history proof. Else Unresolved. No enrichment."
        ),
    }
    (ART / "needs_investigation_resolution.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    # CSV per cell
    csv_path = ART / "needs_investigation_resolution.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "jalali_year",
                "jalali_month",
                "city",
                "scope_type",
                "source_checked",
                "result",
                "source_url",
                "evidence",
                "confidence",
                "race_days",
                "heats",
                "results",
            ]
        )
        for r in classified:
            w.writerow(
                [
                    r["jalali_year"],
                    r["jalali_month"],
                    r.get("city") or "nationwide",
                    r.get("scope_type"),
                    r.get("source_checked"),
                    r.get("result"),
                    r.get("source_url"),
                    json.dumps(r.get("evidence"), ensure_ascii=False)[:500],
                    r.get("confidence"),
                    r.get("race_days"),
                    r.get("heats"),
                    r.get("results"),
                ]
            )

    md = ART / "needs_investigation_resolution.md"
    md.write_text(
        "\n".join(
            [
                "# Needs Investigation Resolution (1328)",
                "",
                f"- Today Jalali: **{summary['Today Jalali']}**",
                "- Enrichment gate: **CLOSED**",
                "",
                "| Metric | Value |",
                "|---|---:|",
                f"| Input Needs Investigation | {summary['Input Needs Investigation']} |",
                f"| Confirmed No-Race | {summary['Confirmed No-Race']} |",
                f"| Confirmed Missing Data | {summary['Confirmed Missing Data']} |",
                f"| Unresolved | {summary['Unresolved']} |",
                f"| New Race Days | {summary['New Race Days']} |",
                f"| New Heats | {summary['New Heats']} |",
                f"| New Results | {summary['New Results']} |",
                f"| Coverage Pct (proxy) | {summary['Coverage Pct Proxy']:.2f} |",
                "",
                "## Rules",
                "",
                "- **Confirmed No-Race**: only future Jalali months (calendar evidence).",
                "- **Confirmed Missing Data**: asbdavani horse history proves races + URL when available.",
                "- **Unresolved**: insufficient evidence — never invent No-Race or fabricate records.",
                "",
                "Per-cell CSV: `needs_investigation_resolution.csv`",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
