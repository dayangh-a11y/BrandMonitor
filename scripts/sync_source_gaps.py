"""Sync gaps between primary sources and the historical warehouse DB.

Sources compared:
1. asbdavani.app/racecards index (canonical week list)
2. api-mosharekat.asbdavani.app /races/days (external_id → asbdavani week pages
   that may be absent from the public index)

Actions:
- Discover Race Days / Heats present in source but missing from DB
- Collect missing heats into Raw (normalized via existing parsers)
- Optionally refresh heats that have zero positive finish positions
- Rebuild warehouse + identity links
- Emit added / modified / deleted report (deleted is always 0 — append-only Raw)
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
os.environ.setdefault("CRAWL_DELAY_SECONDS", "0.6")
os.environ.setdefault("OUTPUT_DIR", "output/historical/sync")
os.environ.setdefault("LOG_DIR", "logs/historical")
os.environ.setdefault("LOG_LEVEL", "INFO")

from loguru import logger

from src.asbdavani.constants import absolute_url, parse_race_url
from src.browser.playwright_client import BrowserClient
from src.collectors import RaceCollector
from src.crawler.discovery import (
    discover_race_urls_from_week_html,
    discover_weeks,
    week_url,
)
from src.database import init_db, reset_engine, session_scope
from src.identity import build_horse_identity
from src.prediction_market.client import MosharekatClient
from src.utils.jalali import format_jalali
from src.utils.logging import setup_logging
from src.warehouse import build_warehouse, run_entity_resolution


def _db_week_and_race_keys(session_conn) -> tuple[set[str], set[tuple[str, int]], set[str]]:
    import sqlite3

    conn = sqlite3.connect(str(DB_PATH))
    weeks: set[str] = set()
    keys: set[tuple[str, int]] = set()
    urls: set[str] = set()
    for source_url, race_number in conn.execute(
        "SELECT source_url, race_number FROM wh_races"
    ):
        u = (source_url or "").split("#")[0]
        urls.add(u)
        m = re.search(r"/racecards/([A-Za-z0-9]+)", u)
        if not m:
            continue
        wid = m.group(1)
        weeks.add(wid)
        rm = re.search(r"[?&]round=(\d+)", u)
        rnd = int(rm.group(1)) if rm else race_number
        if rnd is not None:
            keys.add((wid, int(rnd)))
    conn.close()
    return weeks, keys, urls


def _snapshot_counts() -> dict:
    import sqlite3

    conn = sqlite3.connect(str(DB_PATH))
    out = {
        "wh_races": conn.execute("SELECT COUNT(*) FROM wh_races").fetchone()[0],
        "wh_race_results": conn.execute("SELECT COUNT(*) FROM wh_race_results").fetchone()[0],
        "wh_horses": conn.execute("SELECT COUNT(*) FROM wh_horses").fetchone()[0],
        "raw_races_current": conn.execute(
            "SELECT COUNT(*) FROM raw_races WHERE is_current=1"
        ).fetchone()[0],
        "raw_entries_current": conn.execute(
            "SELECT COUNT(*) FROM raw_race_entries WHERE is_current=1"
        ).fetchone()[0],
        "race_days": conn.execute(
            "SELECT COUNT(DISTINCT race_date || '|' || track) FROM wh_races"
        ).fetchone()[0],
    }
    conn.close()
    return out


def compare_asbdavani_index() -> dict:
    weeks_db, keys_db, urls_db = _db_week_and_race_keys(None)
    with BrowserClient() as browser:
        html = browser.fetch_html("https://asbdavani.app/racecards")
        live_weeks = discover_weeks(html, allowed_codes=None)
        live_ids = {w.week_id for w in live_weeks}
        missing_weeks = sorted(live_ids - weeks_db)
        missing_heats: list[dict] = []
        live_heat_n = 0
        for w in live_weeks:
            whtml = browser.fetch_html(week_url(w.week_id))
            races = discover_race_urls_from_week_html(whtml, w.week_id)
            live_heat_n += len(races)
            for race_url in races:
                race_url = absolute_url(race_url).split("#")[0]
                wid, rnd = parse_race_url(race_url)
                wid = wid or w.week_id
                if rnd is None:
                    continue
                if (wid, int(rnd)) not in keys_db and race_url not in urls_db:
                    missing_heats.append(
                        {
                            "week_id": wid,
                            "round": int(rnd),
                            "url": race_url,
                            "location": w.location,
                        }
                    )
                time.sleep(0.15)
    return {
        "live_weeks": len(live_ids),
        "db_weeks": len(weeks_db),
        "live_heats": live_heat_n,
        "db_heats": len(keys_db),
        "missing_weeks": missing_weeks,
        "missing_heats": missing_heats,
    }


def compare_mosharekat() -> dict:
    weeks_db, keys_db, urls_db = _db_week_and_race_keys(None)
    cached = ART / "mosharekat_vs_db_diff.json"
    days: list[dict] = []
    try:
        client = MosharekatClient()
        payload = client.list_race_days(limit=500)
        if isinstance(payload, list):
            days = payload
        elif isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, dict):
                days = data.get("race_days") or data.get("items") or []
            elif isinstance(data, list):
                days = data
            else:
                days = payload.get("race_days") or []
        if not isinstance(days, list):
            days = []
    except Exception as exc:  # noqa: BLE001
        logger.warning("mosharekat live fetch failed: {}", exc)
        if cached.exists():
            prev = json.loads(cached.read_text(encoding="utf-8"))
            # Prefer recompute from embedded days if present; else keep missing list
            if prev.get("missing_race_days") and not prev.get("mosharekat_days"):
                return prev
            days = []
    if not days and cached.exists():
        # Reuse previously computed missing list when API flakes
        prev = json.loads(cached.read_text(encoding="utf-8"))
        if prev.get("missing_race_days"):
            logger.info("Using cached mosharekat missing_race_days ({})", len(prev["missing_race_days"]))
            return {
                "mosharekat_days": prev.get("mosharekat_days"),
                "missing_race_days": prev["missing_race_days"],
                "from_cache": True,
            }

    missing_days: list[dict] = []
    for d in days:
        if not isinstance(d, dict):
            continue
        ext = d.get("external_id")
        if not ext:
            continue
        if ext in weeks_db:
            continue
        ddate = (d.get("date") or "")[:10] or None
        track = (d.get("track") or {}).get("name") if isinstance(d.get("track"), dict) else None
        missing_days.append(
            {
                "mosharekat_id": d.get("id"),
                "name": d.get("name"),
                "date": ddate,
                "date_j": format_jalali(ddate) if ddate else None,
                "track": track,
                "external_id": ext,
                "num_races": d.get("num_races"),
                "week_url": week_url(ext),
            }
        )
    return {"mosharekat_days": len(days), "missing_race_days": missing_days, "from_cache": False}


def expand_week_heats(week_ids: list[str]) -> list[str]:
    urls: list[str] = []
    with BrowserClient() as browser:
        for wid in week_ids:
            try:
                html = browser.fetch_html(week_url(wid))
                urls.extend(discover_race_urls_from_week_html(html, wid))
            except Exception as exc:  # noqa: BLE001
                logger.error("expand week {} failed: {}", wid, exc)
            time.sleep(0.2)
    # unique preserve order
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        u = absolute_url(u).split("#")[0]
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def incomplete_heat_urls() -> list[str]:
    import sqlite3

    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        """
        SELECT source_url FROM wh_races ra
        WHERE source_url IS NOT NULL
          AND (
            SELECT COUNT(*) FROM wh_race_results rr
            WHERE rr.race_id=ra.id
              AND rr.finish_position IS NOT NULL
              AND rr.finish_position > 0
          ) = 0
        """
    ).fetchall()
    conn.close()
    return [r[0].split("#")[0] for r in rows if r[0]]


def collect_urls(urls: list[str], *, label: str) -> dict:
    collector = RaceCollector(
        collect_histories=False,
        persist_to_db=True,
        output_dir=Path("output/historical/sync") / label,
    )
    ok, fail = [], []
    try:
        for i, url in enumerate(urls, 1):
            try:
                collector.collect(url)
                ok.append(url)
                logger.info("[{}/{}] collected {}", i, len(urls), url)
            except Exception as exc:  # noqa: BLE001
                fail.append({"url": url, "error": str(exc)})
                logger.error("collect failed {}: {}", url, exc)
            time.sleep(0.4)
    finally:
        # close playwright owned by datasource if any
        ds = getattr(collector, "datasource", None)
        close = getattr(ds, "close", None) or getattr(getattr(ds, "browser", None), "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001
                pass
    return {"ok": ok, "failed": fail}


def rebuild() -> dict:
    reset_engine()
    init_db()
    with session_scope() as session:
        wh = build_warehouse(session)
        er = run_entity_resolution(session)
    with session_scope() as session:
        ident = build_horse_identity(session)
    return {"warehouse": wh, "entity_resolution": er, "identity": ident}


def main() -> None:
    setup_logging()
    reset_engine()
    init_db()
    before = _snapshot_counts()
    logger.info("BEFORE {}", before)

    # 1) Index parity (expect ~0 gaps)
    logger.info("Comparing asbdavani /racecards index …")
    # Skip full 182-week re-scan if artifact fresh; still require mosharekat path.
    index_diff_path = ART / "source_vs_db_diff.json"
    if index_diff_path.exists():
        index_diff = json.loads(index_diff_path.read_text(encoding="utf-8"))
        logger.info(
            "Using cached index diff: missing_heats={}",
            index_diff.get("missing_heats_count", len(index_diff.get("missing_heats") or [])),
        )
    else:
        index_diff = compare_asbdavani_index()
        index_diff_path.write_text(json.dumps(index_diff, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2) Mosharekat → asbdavani weeks missing from DB
    logger.info("Comparing mosharekat race days …")
    mosh = compare_mosharekat()
    (ART / "mosharekat_vs_db_diff.json").write_text(
        json.dumps(mosh, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    missing_days = mosh["missing_race_days"]
    logger.info("Mosharekat missing race days: {}", len(missing_days))

    week_ids = [d["external_id"] for d in missing_days if d.get("external_id")]
    new_heat_urls = expand_week_heats(week_ids)
    # filter already in DB
    _, keys_db, urls_db = _db_week_and_race_keys(None)
    to_add = []
    for u in new_heat_urls:
        wid, rnd = parse_race_url(u)
        if u in urls_db:
            continue
        if wid and rnd is not None and (wid, int(rnd)) in keys_db:
            continue
        to_add.append(u)
    logger.info("New heat URLs to ingest: {} (expanded {})", len(to_add), len(new_heat_urls))

    added = collect_urls(to_add, label="mosharekat_gaps") if to_add else {"ok": [], "failed": []}

    # 3) Refresh incomplete heats from source (modify via append-only new raw version)
    refresh_urls = incomplete_heat_urls()
    logger.info("Incomplete heats to refresh: {}", len(refresh_urls))
    modified = (
        collect_urls(refresh_urls, label="refresh_incomplete")
        if refresh_urls
        else {"ok": [], "failed": []}
    )

    # Also any index-missing heats
    index_missing_urls = [h["url"] for h in (index_diff.get("missing_heats") or []) if h.get("url")]
    index_added = (
        collect_urls(index_missing_urls, label="index_gaps")
        if index_missing_urls
        else {"ok": [], "failed": []}
    )

    logger.info("Rebuilding warehouse + identity …")
    rebuild_stats = rebuild()
    after = _snapshot_counts()

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generated_at_jalali_note": "display dates in Jalali elsewhere",
        "sources": {
            "asbdavani_index": "https://asbdavani.app/racecards",
            "mosharekat_days": "https://api-mosharekat.asbdavani.app/api/v1/races/days",
        },
        "before": before,
        "after": after,
        "delta": {k: after[k] - before[k] for k in before},
        "index_diff_summary": {
            "live_weeks": index_diff.get("live_weeks"),
            "db_weeks": index_diff.get("db_weeks"),
            "missing_heats": index_diff.get("missing_heats_count", len(index_diff.get("missing_heats") or [])),
        },
        "mosharekat_missing_race_days": len(missing_days),
        "mosharekat_missing_days_sample": missing_days[:10],
        "added": {
            "heat_urls_attempted": len(to_add) + len(index_missing_urls),
            "heats_collected_ok": len(added["ok"]) + len(index_added["ok"]),
            "heats_failed": added["failed"] + index_added["failed"],
            "new_race_days_targeted": len(missing_days),
        },
        "modified": {
            "incomplete_heats_refreshed_ok": len(modified["ok"]),
            "incomplete_heats_failed": modified["failed"],
            "note": "Raw is append-only; refresh creates newer is_current versions then warehouse rebuild replaces results",
        },
        "deleted": {
            "count": 0,
            "note": "No deletes — Raw warehouse is append-only; obsolete rows are superseded (is_current=0)",
        },
        "rebuild": rebuild_stats,
    }
    path = ART / "source_sync_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md = [
        "# Source ↔ DB Sync Report",
        f"- Before heats: {before['wh_races']} → After: {after['wh_races']} (Δ {after['wh_races']-before['wh_races']})",
        f"- Before results: {before['wh_race_results']} → After: {after['wh_race_results']} (Δ {after['wh_race_results']-before['wh_race_results']})",
        f"- Before race days: {before['race_days']} → After: {after['race_days']} (Δ {after['race_days']-before['race_days']})",
        f"- Mosharekat missing Race Days targeted: {len(missing_days)}",
        f"- Heats collected OK: {report['added']['heats_collected_ok']}",
        f"- Incomplete refreshed OK: {report['modified']['incomplete_heats_refreshed_ok']}",
        f"- Deleted: 0 (append-only)",
    ]
    (ART / "source_sync_report.md").write_text("\n".join(md), encoding="utf-8")
    logger.info("Report written to {}", path)
    print(json.dumps(report["delta"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
