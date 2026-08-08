"""Harvest and parse asbdavani horse /productions pages (offspring race stats)."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Iterable

from src.parsers.html import extract_balanced_json_value, extract_next_flight_text

BASE = "https://asbdavani.app/performance/horses"
UA = "BrandMonitorBreedingValue/0.1 (+research; file-only harvest)"

BLOOD_LABELS = {
    "TURKMEN": "ترکمن",
    "ARAB": "عرب",
    "DOKHOON": "دوخون",
    "THORUGHBREAD": "تروبرد",
    "THOROUGHBRED": "تروبرد",
}

KNOWN_BLOODS = ("TURKMEN", "ARAB", "DOKHOON", "THORUGHBREAD", "THOROUGHBRED")


def productions_url(source_horse_id: str, page: int = 1) -> str:
    return f"{BASE}/{source_horse_id}/productions?page={int(page)}"


def blood_label(code: str | None) -> str:
    if not code:
        return "نامشخص"
    return BLOOD_LABELS.get(str(code).upper(), str(code))


def normalize_blood(code: str | None) -> str | None:
    if not code:
        return None
    key = str(code).upper().strip()
    if key == "THOROUGHBRED":
        return "THORUGHBREAD"
    if key in BLOOD_LABELS or key in KNOWN_BLOODS:
        return "THORUGHBREAD" if key == "THOROUGHBRED" else key
    return key


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


def parse_productions_html(html: str) -> dict[str, Any]:
    """Extract paginated offspring rows from a /productions HTML page."""
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
        if rows and isinstance(rows[0], dict) and "blood" in rows[0]:
            candidates.append(obj)
        elif obj.get("totalPages") is not None and rows == []:
            candidates.append(obj)

    for m in re.finditer(r'\{\s*"data"\s*:\s*\{\s*"data"\s*:\s*\[', flight):
        try:
            obj = extract_balanced_json_value(flight, m.start())
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(obj, dict):
            continue
        inner = obj.get("data")
        if isinstance(inner, dict) and isinstance(inner.get("data"), list):
            rows = inner["data"]
            if rows and isinstance(rows[0], dict) and "blood" in rows[0]:
                candidates.append(inner)
            elif inner.get("totalPages") is not None and rows == []:
                candidates.append(inner)

    if not candidates:
        return {
            "parse_status": "EMPTY",
            "page": None,
            "page_size": None,
            "total_pages": None,
            "offspring": [],
        }

    best = max(
        candidates,
        key=lambda o: (
            len(o.get("data") or []),
            int(o.get("totalPages") or 0),
        ),
    )
    offspring = []
    for row in best.get("data") or []:
        if not isinstance(row, dict):
            continue
        offspring.append(
            {
                "source_id": row.get("id"),
                "name": row.get("name"),
                "blood": normalize_blood(row.get("blood")),
                "blood_raw": row.get("blood"),
                "sex": row.get("sex"),
                "birthdate": row.get("birthdate"),
                "breed_code": row.get("breed"),
                "wins": int(row.get("p1") or 0),
                "seconds": int(row.get("p2") or 0),
                "thirds": int(row.get("p3") or 0),
                "starts": int(row.get("starts") or 0),
                "ior": row.get("ior"),
                "father_name": (row.get("father") or {}).get("name")
                if isinstance(row.get("father"), dict)
                else None,
                "mother_name": (row.get("mother") or {}).get("name")
                if isinstance(row.get("mother"), dict)
                else None,
                "father_id": (row.get("father") or {}).get("id")
                if isinstance(row.get("father"), dict)
                else row.get("fatherId"),
                "mother_id": (row.get("mother") or {}).get("id")
                if isinstance(row.get("mother"), dict)
                else row.get("motherId"),
            }
        )

    return {
        "parse_status": "OK" if offspring or int(best.get("totalPages") or 0) == 0 else "OK",
        "page": best.get("page"),
        "page_size": best.get("pageSize"),
        "total_pages": best.get("totalPages"),
        "offspring": offspring,
    }


def _source_id_from_entity_id(entity_id: str) -> str | None:
    if not entity_id:
        return None
    if entity_id.startswith("src:"):
        return entity_id.split(":", 1)[1]
    return None


def load_parent_targets(entities_path: Path, relationships_path: Path) -> list[dict[str, Any]]:
    """Parents that appear in pedigree relationships and have a harvestable source id."""
    from collections import defaultdict

    counts: dict[str, int] = defaultdict(int)
    roles: dict[str, set[str]] = defaultdict(set)
    names: dict[str, str] = {}
    with relationships_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            eid = row.get("parent_entity_id")
            if not eid:
                continue
            counts[eid] += 1
            field = row.get("field")
            if field:
                roles[eid].add(str(field).upper())
            if row.get("parent_name"):
                names[eid] = row["parent_name"]

    entities = json.loads(entities_path.read_text(encoding="utf-8")).get("entities") or []
    ent_by_id = {e["entity_id"]: e for e in entities if e.get("entity_id")}

    out: list[dict[str, Any]] = []
    for eid, n in counts.items():
        sid = _source_id_from_entity_id(eid)
        if not sid:
            continue
        ent = ent_by_id.get(eid) or {}
        role_hints = set(ent.get("role_hints") or [])
        role_hints |= roles.get(eid, set())
        if "SIRE" in role_hints or "sire" in {r.lower() for r in role_hints}:
            role = "SIRE"
        elif "DAM" in role_hints or "dam" in {r.lower() for r in role_hints}:
            role = "DAM"
        else:
            # relationships field
            rel_roles = roles.get(eid, set())
            if "SIRE" in rel_roles or "sire" in {r.lower() for r in rel_roles}:
                role = "SIRE"
            elif "DAM" in rel_roles or "dam" in {r.lower() for r in rel_roles}:
                role = "DAM"
            else:
                continue
        out.append(
            {
                "entity_id": eid,
                "source_id": sid,
                "canonical_name": ent.get("canonical_name") or names.get(eid),
                "role": role,
                "known_offspring_in_pedigree": n,
            }
        )
    out.sort(key=lambda r: (-int(r["known_offspring_in_pedigree"]), r["canonical_name"] or ""))
    return out


def load_done_parent_ids(path: Path) -> set[str]:
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
            sid = row.get("parent_source_id")
            if sid and row.get("harvest_status") in {"OK", "EMPTY"}:
                done.add(str(sid))
    return done


def harvest_parent_productions(parent: dict[str, Any]) -> dict[str, Any]:
    """Fetch all production pages for one parent and merge offspring rows."""
    sid = parent["source_id"]
    all_rows: list[dict[str, Any]] = []
    total_pages = 1
    errors: list[str] = []
    page = 1
    while page <= total_pages:
        url = productions_url(sid, page)
        try:
            html = fetch_html(url)
            parsed = parse_productions_html(html)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"page {page}: {exc}"[:300])
            break
        if parsed.get("total_pages") is not None:
            try:
                total_pages = max(1, int(parsed["total_pages"]))
            except (TypeError, ValueError):
                total_pages = 1
        all_rows.extend(parsed.get("offspring") or [])
        if not parsed.get("offspring") and page == 1 and (parsed.get("total_pages") in (0, None)):
            break
        page += 1
        if page > 200:  # hard safety
            errors.append("page_cap_200")
            break

    # de-dupe by offspring source_id
    by_id: dict[str, dict[str, Any]] = {}
    anon = 0
    for row in all_rows:
        key = row.get("source_id")
        if not key:
            anon += 1
            key = f"anon:{anon}:{row.get('name')}"
        by_id[str(key)] = row

    status = "OK"
    if errors and not by_id:
        status = "FETCH_ERROR"
    elif not by_id:
        status = "EMPTY"

    return {
        "parent_source_id": sid,
        "parent_entity_id": parent.get("entity_id"),
        "parent_name": parent.get("canonical_name"),
        "role": parent.get("role"),
        "known_offspring_in_pedigree": parent.get("known_offspring_in_pedigree"),
        "harvest_status": status,
        "harvest_errors": errors,
        "total_pages_seen": total_pages if status != "FETCH_ERROR" else None,
        "offspring_count": len(by_id),
        "offspring": list(by_id.values()),
        "source": "asbdavani_productions_page",
    }


def harvest_many(
    parents: Iterable[dict[str, Any]],
    out_jsonl: Path,
    *,
    workers: int = 6,
    limit: int | None = None,
    progress_every: int = 25,
    min_known_offspring: int = 1,
) -> dict[str, Any]:
    """Append per-parent productions harvest rows with resume support."""
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    done = load_done_parent_ids(out_jsonl)
    todo = [
        p
        for p in parents
        if p["source_id"] not in done
        and int(p.get("known_offspring_in_pedigree") or 0) >= min_known_offspring
    ]
    if limit is not None:
        todo = todo[:limit]

    stats = {
        "already_done": len(done),
        "queued": len(todo),
        "ok": 0,
        "empty": 0,
        "errors": 0,
        "offspring_rows": 0,
    }
    if not todo:
        return stats

    in_flight_cap = max(workers * 2, workers)
    with out_jsonl.open("a", encoding="utf-8") as fh, ThreadPoolExecutor(max_workers=workers) as ex:
        it = iter(todo)
        futures = {}
        for _ in range(min(in_flight_cap, len(todo))):
            try:
                parent = next(it)
            except StopIteration:
                break
            futures[ex.submit(harvest_parent_productions, parent)] = parent

        finished = 0
        while futures:
            done_set, _ = wait(futures, return_when=FIRST_COMPLETED)
            for fut in done_set:
                parent = futures.pop(fut)
                try:
                    row = fut.result()
                except Exception as exc:  # noqa: BLE001
                    row = {
                        "parent_source_id": parent["source_id"],
                        "parent_entity_id": parent.get("entity_id"),
                        "parent_name": parent.get("canonical_name"),
                        "role": parent.get("role"),
                        "known_offspring_in_pedigree": parent.get("known_offspring_in_pedigree"),
                        "harvest_status": "FETCH_ERROR",
                        "harvest_errors": [str(exc)[:300]],
                        "total_pages_seen": None,
                        "offspring_count": 0,
                        "offspring": [],
                        "source": "asbdavani_productions_page",
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
                stats["offspring_rows"] += int(row.get("offspring_count") or 0)
                finished += 1
                if finished % progress_every == 0:
                    print(
                        f"[breeding-harvest] {finished}/{len(todo)} "
                        f"ok={stats['ok']} empty={stats['empty']} err={stats['errors']}",
                        flush=True,
                    )
                try:
                    nxt = next(it)
                except StopIteration:
                    continue
                futures[ex.submit(harvest_parent_productions, nxt)] = nxt

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
