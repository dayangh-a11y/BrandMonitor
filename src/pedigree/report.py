"""Coverage, network, quality, and audit reports for pedigree foundation."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def audit_local_sources(db_path: Path) -> dict[str, Any]:
    """Audit ALL local raw/warehouse/identity fields for pedigree coverage."""
    conn = sqlite3.connect(str(db_path))
    sources: list[dict[str, Any]] = []

    def add(
        source: str,
        field: str,
        total: int,
        filled: int,
        examples: list[Any],
        notes: str = "",
    ) -> None:
        cov = round(100.0 * filled / total, 4) if total else 0.0
        sources.append(
            {
                "source": source,
                "field": field,
                "number_of_records": total,
                "filled": filled,
                "coverage_pct": cov,
                "example_values": examples,
                "notes": notes,
            }
        )

    # raw_horses.sire / dam
    total = conn.execute("SELECT COUNT(*) FROM raw_horses").fetchone()[0]
    for field in ("sire", "dam"):
        filled = conn.execute(
            f"SELECT COUNT(*) FROM raw_horses WHERE {field} IS NOT NULL AND TRIM({field}) != ''"
        ).fetchone()[0]
        ex = [
            r[0]
            for r in conn.execute(
                f"SELECT {field} FROM raw_horses WHERE {field} IS NOT NULL AND TRIM({field}) != '' LIMIT 5"
            )
        ]
        add("raw_horses", field, total, filled, ex, "Column exists; race-card ingest never populated")

    # payload keys
    # Sample payloads for father/mother keys
    payload_hit = conn.execute(
        """
        SELECT COUNT(*) FROM raw_horses
        WHERE payload_json LIKE '%father%'
           OR payload_json LIKE '%mother%'
           OR payload_json LIKE '%"sire"%'
           OR payload_json LIKE '%"dam"%'
           OR payload_json LIKE '%pedigree%'
        """
    ).fetchone()[0]
    add(
        "raw_horses.payload_json",
        "father|mother|sire|dam|pedigree",
        total,
        payload_hit,
        [],
        "Race-entry payloads only contain card fields; no pedigree keys observed",
    )

    # profile urls point at performance pages but not /pedigree
    ped_url = conn.execute(
        "SELECT COUNT(*) FROM raw_horses WHERE profile_url LIKE '%/pedigree%' OR source_url LIKE '%/pedigree%'"
    ).fetchone()[0]
    add(
        "raw_horses",
        "profile_url|/pedigree",
        total,
        ped_url,
        [],
        "Dedicated /pedigree pages exist on asbdavani but were never crawled into DB",
    )

    # wh_horse_pedigree
    try:
        wh_total = conn.execute("SELECT COUNT(*) FROM wh_horse_pedigree").fetchone()[0]
        for field in ("sire_name", "dam_name", "sire_horse_id", "dam_horse_id"):
            if field.endswith("_id"):
                filled = conn.execute(
                    f"SELECT COUNT(*) FROM wh_horse_pedigree WHERE {field} IS NOT NULL"
                ).fetchone()[0]
            else:
                filled = conn.execute(
                    f"SELECT COUNT(*) FROM wh_horse_pedigree WHERE {field} IS NOT NULL AND TRIM({field}) != ''"
                ).fetchone()[0]
            add("wh_horse_pedigree", field, wh_total, filled, [], "Warehouse placeholder structure")
    except sqlite3.OperationalError:
        pass

    # id_horses normalized
    id_total = conn.execute("SELECT COUNT(*) FROM id_horses").fetchone()[0]
    for field in ("sire_normalized", "dam_normalized"):
        filled = conn.execute(
            f"SELECT COUNT(*) FROM id_horses WHERE {field} IS NOT NULL AND TRIM({field}) != ''"
        ).fetchone()[0]
        add("id_horses", field, id_total, filled, [], "Identity layer empty until pedigree harvest")

    # false-positive LIKE hits inside source ids containing 'dam'
    dam_substr = conn.execute(
        "SELECT COUNT(*) FROM raw_horses WHERE source_horse_id LIKE '%dam%'"
    ).fetchone()[0]
    add(
        "raw_horses.source_horse_id",
        "substring 'dam'",
        total,
        dam_substr,
        [
            r[0]
            for r in conn.execute(
                "SELECT source_horse_id FROM raw_horses WHERE source_horse_id LIKE '%dam%' LIMIT 3"
            )
        ],
        "NOT pedigree — accidental substring inside opaque source ids",
    )

    conn.close()
    return {
        "database": str(db_path),
        "sources": sources,
        "live_source_note": (
            "asbdavani.app exposes /performance/horses/{id}/pedigree charts with "
            "sire/dam trees. This is the primary pedigree source for harvest."
        ),
        "parser_capability": {
            "src/asbdavani/parsers/horse.py": "Reads horse.father.name / horse.mother.name from history payloads (currently absent on history pages)",
            "src/pedigree/parse.py": "Parses /pedigree HTML chart into sire/dam/grandparents",
        },
    }


def coverage_report(
    *,
    horses: dict[int, dict[str, Any]],
    horse_parents: dict[int, dict[str, Any]],
    harvest: list[dict[str, Any]],
    identity: dict[str, Any],
    db_path: Path,
) -> dict[str, Any]:
    total = len(horses)
    with_sire = sum(1 for h, p in horse_parents.items() if p.get("sire_id") and h in horses)
    with_dam = sum(1 for h, p in horse_parents.items() if p.get("dam_id") and h in horses)
    with_both = sum(
        1
        for h, p in horse_parents.items()
        if p.get("sire_id") and p.get("dam_id") and h in horses
    )
    with_neither = total - len(
        {
            h
            for h, p in horse_parents.items()
            if (p.get("sire_id") or p.get("dam_id")) and h in horses
        }
    )

    def pct(n: int) -> float:
        return round(100.0 * n / total, 4) if total else 0.0

    # By source (harvest status)
    by_source = {
        "asbdavani_pedigree_page": {
            "harvested": len(harvest),
            "with_sire_in_chart": sum(1 for r in harvest if r.get("sire")),
            "with_dam_in_chart": sum(1 for r in harvest if r.get("dam")),
            "with_both_in_chart": sum(1 for r in harvest if r.get("sire") and r.get("dam")),
        }
    }

    # Track / year from starts
    source_to_horse = identity["source_to_horse"]
    starts = identity["starts"]
    by_track: dict[str, Counter] = defaultdict(Counter)
    by_year: dict[str, Counter] = defaultdict(Counter)
    for hid, st_list in starts.items():
        p = horse_parents.get(hid, {})
        has_s = bool(p.get("sire_id"))
        has_d = bool(p.get("dam_id"))
        tracks = {s.get("track") or "UNKNOWN" for s in st_list}
        years = set()
        for s in st_list:
            rd = s.get("race_date") or ""
            years.add(str(rd)[:4] if rd else "UNKNOWN")
        for t in tracks:
            by_track[t]["horses"] += 1
            by_track[t]["with_sire"] += int(has_s)
            by_track[t]["with_dam"] += int(has_d)
            by_track[t]["with_both"] += int(has_s and has_d)
        for y in years:
            by_year[y]["horses"] += 1
            by_year[y]["with_sire"] += int(has_s)
            by_year[y]["with_dam"] += int(has_d)
            by_year[y]["with_both"] += int(has_s and has_d)

    # Breed from meta cities / blood hints if present
    by_breed: dict[str, Counter] = defaultdict(Counter)
    for hid, h in horses.items():
        meta = h.get("meta") or {}
        cities = meta.get("cities") or []
        breed = "UNKNOWN"
        # heuristic labels from city tags only as grouping dimension, not pedigree invent
        if cities:
            breed = str(cities[0])
        p = horse_parents.get(hid, {})
        by_breed[breed]["horses"] += 1
        by_breed[breed]["with_sire"] += int(bool(p.get("sire_id")))
        by_breed[breed]["with_dam"] += int(bool(p.get("dam_id")))
        by_breed[breed]["with_both"] += int(bool(p.get("sire_id") and p.get("dam_id")))

    return {
        "total_canonical_horses": total,
        "horses_with_sire": with_sire,
        "horses_with_dam": with_dam,
        "horses_with_both": with_both,
        "horses_with_neither": with_neither,
        "sire_coverage_pct": pct(with_sire),
        "dam_coverage_pct": pct(with_dam),
        "complete_pedigree_coverage_pct": pct(with_both),
        "by_source": by_source,
        "by_track": {k: dict(v) for k, v in sorted(by_track.items())},
        "by_year": {k: dict(v) for k, v in sorted(by_year.items())},
        "by_breed_proxy_city": {k: dict(v) for k, v in sorted(by_breed.items())},
        "notes": [
            "Breed dimension uses identity meta city proxy when explicit breed is unavailable.",
            "Coverage counts only resolved parent relationships without conflicts.",
        ],
    }


def depth_report(
    harvest: list[dict[str, Any]],
    source_to_horse: dict[str, int],
) -> dict[str, Any]:
    depth_counts = Counter()
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in harvest:
        has_p = bool(row.get("sire") or row.get("dam"))
        has_gp = any(
            row.get(k) for k in ("sire_sire", "sire_dam", "dam_sire", "dam_dam")
        )
        # Probe whether grandparents themselves imply depth 3 is available on page:
        # this chart maxes at gen2 in the 4-column table → max reliable depth from
        # a single page is 2 unless we follow parent pages.
        if has_gp:
            depth = 2
        elif has_p:
            depth = 1
        else:
            depth = 0
        depth_counts[str(depth)] += 1
        if len(examples[str(depth)]) < 3:
            examples[str(depth)].append(
                {
                    "subject_source_id": row.get("subject_source_id"),
                    "subject_name": row.get("subject_name"),
                    "sire": (row.get("sire") or {}).get("name"),
                    "dam": (row.get("dam") or {}).get("name"),
                }
            )
    return {
        "depth_counts": dict(depth_counts),
        "max_reliable_depth_single_page": 2,
        "max_reliable_depth_with_follow": "3+ (requires crawling parent /pedigree pages; not invented)",
        "examples": dict(examples),
        "note": "Depth 3+ is only reliable when parent pedigree pages are harvested; this phase uses subject charts (depth ≤ 2) plus entity links.",
    }


def network_report(
    *,
    entities: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    starts: dict[int, list[dict[str, Any]]],
    horses: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    """Static descriptive offspring stats (NOT as-of race-date; not for prediction)."""
    offspring: dict[str, list[int]] = defaultdict(list)
    for rel in relationships:
        eid = rel.get("parent_entity_id")
        hid = rel.get("horse_id")
        if eid and hid is not None:
            offspring[str(eid)].append(int(hid))

    def stats_for(role: str) -> list[dict[str, Any]]:
        out = []
        for ent in entities:
            if role not in ent.get("role_hints", []):
                continue
            kids = sorted(set(offspring.get(ent["entity_id"], [])))
            n_starts = n_wins = n_top3 = 0
            for kid in kids:
                for st in starts.get(kid, []):
                    n_starts += 1
                    fp = st.get("finish_position")
                    try:
                        fp_i = int(fp) if fp is not None else None
                    except (TypeError, ValueError):
                        fp_i = None
                    if fp_i == 1:
                        n_wins += 1
                    if fp_i is not None and fp_i <= 3:
                        n_top3 += 1
            out.append(
                {
                    "entity_id": ent["entity_id"],
                    "canonical_name": ent.get("canonical_name"),
                    "role": role,
                    "number_of_known_offspring": len(kids),
                    "number_of_starts": n_starts,
                    "wins": n_wins,
                    "top3": n_top3,
                    "win_rate": round(n_wins / n_starts, 4) if n_starts else None,
                    "top3_rate": round(n_top3 / n_starts, 4) if n_starts else None,
                    "stats_scope": "STATIC_DESCRIPTIVE_NOT_ASOF",
                }
            )
        out.sort(key=lambda r: (-r["number_of_known_offspring"], r["canonical_name"] or ""))
        return out

    sire_stats = stats_for("SIRE")
    dam_stats = stats_for("DAM")
    return {
        "sire_network": sire_stats[:200],
        "dam_network": dam_stats[:200],
        "sire_entities_total": sum(1 for e in entities if "SIRE" in e.get("role_hints", [])),
        "dam_entities_total": sum(1 for e in entities if "DAM" in e.get("role_hints", [])),
        "warning": (
            "These statistics are static descriptive only. "
            "When used for prediction they MUST be recomputed as-of each race date "
            "to avoid leaking future offspring results."
        ),
    }


def quality_summary(relationships: list[dict[str, Any]], conflicts: list[dict[str, Any]]) -> dict[str, Any]:
    c = Counter(r.get("quality") or "MISSING" for r in relationships)
    conflicted_horses = {c["horse_id"] for c in conflicts}
    return {
        "relationship_quality_counts": dict(c),
        "horses_with_conflicts": len(conflicted_horses),
        "scale": ["HIGH", "MEDIUM", "LOW", "MISSING"],
        "definition": {
            "HIGH": "Source pedigree page + parent source_id + no conflict",
            "MEDIUM": "Named parent without stable source_id (or external-only link)",
            "LOW": "Conflict present or weak evidence",
            "MISSING": "No source pedigree parent",
        },
        "note": "DATA QUALITY indicator — NOT a prediction probability.",
    }


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
