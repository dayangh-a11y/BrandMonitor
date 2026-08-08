"""Harvest paginated asbdavani horse performance histories (finish times)."""

from __future__ import annotations

import json
import math
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Iterable

from src.asbdavani.constants import BLOOD_SURFACE_HINT, format_race_time
from src.breeding.productions import BLOOD_LABELS, blood_label, normalize_blood
from src.parsers.html import extract_balanced_json_value, extract_next_flight_text

BASE = "https://asbdavani.app/performance/horses"
UA = "BrandMonitorSpeedRecords/0.1 (+research; file-only harvest)"

# Plausible racing speeds (m/s); filters garbage clocks.
# ~18.0 m/s ≈ 55.6s / 1000m (above typical elite Thoroughbred sprint).
MIN_MPS = 11.0
MAX_MPS = 18.0
MIN_TIME_S = 50.0
MAX_TIME_S = 360.0
MIN_DISTANCE = 800
MAX_DISTANCE = 3200


def history_url(source_horse_id: str, page: int = 1) -> str:
    return f"{BASE}/{source_horse_id}?page={int(page)}"


def fetch_html(url: str, *, timeout: float = 30.0, retries: int = 3) -> str:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": UA,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "fa,en;q=0.8",
                    "Connection": "close",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, ConnectionResetError, OSError) as exc:
            last = exc
            time.sleep(0.4 * (2**attempt))
    raise RuntimeError(f"fetch failed after {retries} retries: {url}: {last}")


def _track_from_week_name(week_name: str | None) -> str | None:
    if not week_name:
        return None
    m = re.search(r"هفته\s+\d+\s+(.+?)\s+\d{4}", week_name)
    return m.group(1).strip() if m else None


def parse_history_html(html: str) -> dict[str, Any]:
    """Extract one page of race-history rows with clock times."""
    flight = extract_next_flight_text(html)
    candidates: list[dict[str, Any]] = []

    for m in re.finditer(r'\{\s*"data"\s*:\s*\[', flight):
        try:
            obj = extract_balanced_json_value(flight, m.start())
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(obj, dict) or not isinstance(obj.get("data"), list):
            continue
        rows = obj["data"]
        if not rows:
            if obj.get("totalPages") is not None:
                candidates.append(obj)
            continue
        row0 = rows[0]
        if isinstance(row0, dict) and (
            "rank" in row0 or "entranceRating" in row0 or "race" in row0
        ):
            candidates.append(obj)

    if not candidates:
        return {
            "parse_status": "EMPTY",
            "page": None,
            "page_size": None,
            "total_pages": None,
            "starts": [],
        }

    best = max(
        candidates,
        key=lambda o: (
            len(o.get("data") or []),
            int(o.get("totalPages") or 0),
        ),
    )
    starts: list[dict[str, Any]] = []
    for row in best.get("data") or []:
        if not isinstance(row, dict):
            continue
        race = row.get("race") or {}
        week = race.get("week") or {}
        plan = race.get("plan") or {}
        time_ms = row.get("time")
        try:
            time_ms_i = int(time_ms) if time_ms is not None else 0
        except (TypeError, ValueError):
            time_ms_i = 0
        time_s = (time_ms_i / 1000.0) if time_ms_i > 0 else None
        distance = plan.get("distance")
        try:
            distance_i = int(distance) if distance is not None else None
        except (TypeError, ValueError):
            distance_i = None
        blood_raw = plan.get("blood")
        blood = normalize_blood(blood_raw)
        finish = row.get("rank")
        try:
            finish_i = int(finish) if finish is not None else None
        except (TypeError, ValueError):
            finish_i = None
        if finish_i == 0 and row.get("isRun") is False:
            finish_i = None

        mps = None
        if time_s and distance_i and time_s > 0:
            mps = round(distance_i / time_s, 4)

        starts.append(
            {
                "result_id": row.get("id"),
                "race_id": race.get("id"),
                "race_name": race.get("name") or plan.get("name") or week.get("name"),
                "race_date": week.get("date"),
                "track": _track_from_week_name(week.get("name")),
                "distance": distance_i,
                "blood": blood,
                "blood_raw": blood_raw,
                "breed": blood_label(blood) if blood else None,
                "finish_position": finish_i,
                "time_ms": time_ms_i if time_ms_i > 0 else None,
                "time_s": time_s,
                "time_fmt": format_race_time(time_ms_i if time_ms_i > 0 else None),
                "speed_mps": mps,
                "rating": row.get("entranceRating"),
            }
        )

    return {
        "parse_status": "OK",
        "page": best.get("page"),
        "page_size": best.get("pageSize"),
        "total_pages": best.get("totalPages"),
        "starts": starts,
    }


def is_plausible_timed_start(st: dict[str, Any]) -> bool:
    t = st.get("time_s")
    d = st.get("distance")
    mps = st.get("speed_mps")
    if t is None or d is None or mps is None:
        return False
    if not (MIN_TIME_S <= float(t) <= MAX_TIME_S):
        return False
    if not (MIN_DISTANCE <= int(d) <= MAX_DISTANCE):
        return False
    if not (MIN_MPS <= float(mps) <= MAX_MPS):
        return False
    return True


def load_horse_targets_from_productions(
    productions_path: Path,
    *,
    min_starts: int = 1,
) -> list[dict[str, Any]]:
    """Unique raced horses with blood label from productions harvest."""
    best: dict[str, dict[str, Any]] = {}
    with productions_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            for o in row.get("offspring") or []:
                sid = o.get("source_id")
                if not sid:
                    continue
                starts = int(o.get("starts") or 0)
                if starts < min_starts:
                    continue
                blood = normalize_blood(o.get("blood"))
                if not blood or blood not in BLOOD_LABELS:
                    continue
                prev = best.get(sid)
                if prev is None or starts > int(prev.get("declared_starts") or 0):
                    best[sid] = {
                        "source_id": sid,
                        "name": o.get("name"),
                        "blood": blood,
                        "breed": blood_label(blood),
                        "sex": o.get("sex"),
                        "birthdate": o.get("birthdate"),
                        "declared_starts": starts,
                        "declared_wins": int(o.get("wins") or 0),
                    }
    out = list(best.values())
    out.sort(key=lambda r: (-int(r["declared_starts"]), r["name"] or ""))
    return out


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
            sid = row.get("source_id")
            if sid and row.get("harvest_status") in {"OK", "EMPTY"}:
                done.add(str(sid))
    return done


def harvest_horse_history(horse: dict[str, Any]) -> dict[str, Any]:
    sid = horse["source_id"]
    all_starts: list[dict[str, Any]] = []
    total_pages = 1
    errors: list[str] = []
    page = 1
    while page <= total_pages:
        url = history_url(sid, page)
        try:
            html = fetch_html(url)
            parsed = parse_history_html(html)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"page {page}: {exc}"[:300])
            break
        if parsed.get("total_pages") is not None:
            try:
                total_pages = max(1, int(parsed["total_pages"]))
            except (TypeError, ValueError):
                total_pages = 1
        all_starts.extend(parsed.get("starts") or [])
        if not parsed.get("starts") and page == 1 and (parsed.get("total_pages") in (0, None)):
            break
        page += 1
        if page > 100:
            errors.append("page_cap_100")
            break

    by_id: dict[str, dict[str, Any]] = {}
    anon = 0
    for st in all_starts:
        key = st.get("result_id")
        if not key:
            anon += 1
            key = f"anon:{anon}:{st.get('race_date')}:{st.get('distance')}"
        by_id[str(key)] = st

    starts = list(by_id.values())
    timed = [s for s in starts if is_plausible_timed_start(s)]
    status = "OK"
    if errors and not starts:
        status = "FETCH_ERROR"
    elif not starts:
        status = "EMPTY"

    return {
        "source_id": sid,
        "name": horse.get("name"),
        "blood": horse.get("blood"),
        "breed": horse.get("breed"),
        "sex": horse.get("sex"),
        "birthdate": horse.get("birthdate"),
        "declared_starts": horse.get("declared_starts"),
        "harvest_status": status,
        "harvest_errors": errors,
        "total_pages_seen": total_pages if status != "FETCH_ERROR" else None,
        "starts_count": len(starts),
        "timed_starts_count": len(timed),
        "starts": starts,
        "source": "asbdavani_horse_history",
    }


def harvest_many(
    horses: Iterable[dict[str, Any]],
    out_jsonl: Path,
    *,
    workers: int = 8,
    limit: int | None = None,
    progress_every: int = 50,
) -> dict[str, Any]:
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    done = load_done_ids(out_jsonl)
    todo = [h for h in horses if h["source_id"] not in done]
    if limit is not None:
        todo = todo[:limit]

    stats = {
        "already_done": len(done),
        "queued": len(todo),
        "ok": 0,
        "empty": 0,
        "errors": 0,
        "timed_starts": 0,
    }
    if not todo:
        return stats

    in_flight_cap = max(workers * 2, workers)
    with out_jsonl.open("a", encoding="utf-8") as fh, ThreadPoolExecutor(max_workers=workers) as ex:
        it = iter(todo)
        futures: dict[Any, dict[str, Any]] = {}
        for _ in range(min(in_flight_cap, len(todo))):
            try:
                horse = next(it)
            except StopIteration:
                break
            futures[ex.submit(harvest_horse_history, horse)] = horse

        finished = 0
        while futures:
            done_set, _ = wait(futures, return_when=FIRST_COMPLETED)
            for fut in done_set:
                horse = futures.pop(fut)
                try:
                    row = fut.result()
                except Exception as exc:  # noqa: BLE001
                    row = {
                        "source_id": horse["source_id"],
                        "name": horse.get("name"),
                        "blood": horse.get("blood"),
                        "breed": horse.get("breed"),
                        "sex": horse.get("sex"),
                        "birthdate": horse.get("birthdate"),
                        "declared_starts": horse.get("declared_starts"),
                        "harvest_status": "FETCH_ERROR",
                        "harvest_errors": [str(exc)[:300]],
                        "total_pages_seen": None,
                        "starts_count": 0,
                        "timed_starts_count": 0,
                        "starts": [],
                        "source": "asbdavani_horse_history",
                    }
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
                st = row.get("harvest_status")
                if st == "OK":
                    stats["ok"] += 1
                elif st == "EMPTY":
                    stats["empty"] += 1
                else:
                    stats["errors"] += 1
                stats["timed_starts"] += int(row.get("timed_starts_count") or 0)
                finished += 1
                if finished % progress_every == 0:
                    print(
                        f"[speed-harvest] {finished}/{len(todo)} "
                        f"ok={stats['ok']} empty={stats['empty']} err={stats['errors']} "
                        f"timed={stats['timed_starts']}",
                        flush=True,
                    )
                try:
                    nxt = next(it)
                except StopIteration:
                    continue
                futures[ex.submit(harvest_horse_history, nxt)] = nxt

    return stats


def load_harvest(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def estimated_pages(declared_starts: int) -> int:
    return max(1, math.ceil(max(0, declared_starts) / 20))
