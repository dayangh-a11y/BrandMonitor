"""Harvest pedigree pages from asbdavani into local JSONL (no DB writes)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable

from src.pedigree.parse import parse_pedigree_html

BASE = "https://asbdavani.app/performance/horses"
UA = "BrandMonitorPedigreeFoundation/0.1 (+research; file-only harvest)"


def pedigree_url(source_horse_id: str) -> str:
    return f"{BASE}/{source_horse_id}/pedigree"


def fetch_html(url: str, *, timeout: float = 45.0, retries: int = 4) -> str:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": UA,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "fa,en;q=0.8",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, ConnectionResetError, OSError) as exc:
            last = exc
            time.sleep(min(32.0, 1.5 * (2**attempt)))
    raise RuntimeError(f"fetch failed after {retries} retries: {url}: {last}")


def harvest_one(source_horse_id: str) -> dict[str, Any]:
    url = pedigree_url(source_horse_id)
    try:
        html = fetch_html(url)
        parsed = parse_pedigree_html(html, source_horse_id)
        parsed["source_url"] = url
        parsed["source"] = "asbdavani_pedigree_page"
        parsed["harvest_error"] = None
        return parsed
    except Exception as exc:  # noqa: BLE001
        return {
            "subject_source_id": source_horse_id,
            "subject_name": None,
            "sire": None,
            "dam": None,
            "sire_sire": None,
            "sire_dam": None,
            "dam_sire": None,
            "dam_dam": None,
            "parse_status": "FETCH_ERROR",
            "named_ancestor_count": 0,
            "source_url": url,
            "source": "asbdavani_pedigree_page",
            "harvest_error": str(exc)[:500],
        }


def load_done_ids(path: Path) -> set[str]:
    done: set[str] = set()
    if not path.exists():
        return done
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = row.get("subject_source_id")
            if sid:
                done.add(str(sid))
    return done


def harvest_many(
    source_horse_ids: Iterable[str],
    out_jsonl: Path,
    *,
    workers: int = 6,
    limit: int | None = None,
) -> dict[str, Any]:
    """Append pedigree harvest rows to ``out_jsonl`` with resume support."""
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    done = load_done_ids(out_jsonl)
    todo = [sid for sid in source_horse_ids if sid not in done]
    if limit is not None:
        todo = todo[:limit]

    stats = {
        "already_done": len(done),
        "queued": len(todo),
        "ok": 0,
        "empty": 0,
        "errors": 0,
        "with_sire": 0,
        "with_dam": 0,
        "with_both": 0,
    }
    if not todo:
        return stats

    with out_jsonl.open("a", encoding="utf-8") as fh, ThreadPoolExecutor(
        max_workers=workers
    ) as pool:
        futures = {pool.submit(harvest_one, sid): sid for sid in todo}
        for fut in as_completed(futures):
            row = fut.result()
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            status = row.get("parse_status")
            if status == "FETCH_ERROR":
                stats["errors"] += 1
            elif status == "EMPTY_CHART" or not row.get("named_ancestor_count"):
                stats["empty"] += 1
            else:
                stats["ok"] += 1
            if row.get("sire"):
                stats["with_sire"] += 1
            if row.get("dam"):
                stats["with_dam"] += 1
            if row.get("sire") and row.get("dam"):
                stats["with_both"] += 1
    return stats
