"""Phase 2 — data quality, context coverage, anomaly reports (read-only DB)."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.night_run.paths import DB_PATH, NIGHT_DIR


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn(db: Path) -> sqlite3.Connection:
    c = sqlite3.connect(str(db))
    c.row_factory = sqlite3.Row
    return c


def _pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 4) if d else 0.0


def audit_context(conn: sqlite3.Connection) -> dict[str, Any]:
    total_results = conn.execute("SELECT COUNT(*) FROM wh_race_results").fetchone()[0]
    total_races = conn.execute("SELECT COUNT(*) FROM wh_races").fetchone()[0]
    total_horses = conn.execute(
        "SELECT COUNT(*) FROM id_horses WHERE status='active' OR status IS NULL"
    ).fetchone()[0]

    # Join results to races for context fields
    rows = conn.execute(
        """
        SELECT rr.id AS result_id,
               rr.race_id,
               rr.horse_id AS wh_horse_id,
               rr.finish_position,
               rr.weight,
               rr.number,
               rr.jockey_id,
               rr.trainer_id,
               rr.owner_id,
               ra.distance,
               ra.track,
               ra.racecourse_code,
               ra.name AS race_name,
               ra.race_date,
               ra.surface,
               wh.name AS horse_name,
               wh.source_horse_id
        FROM wh_race_results rr
        JOIN wh_races ra ON ra.id = rr.race_id
        JOIN wh_horses wh ON wh.id = rr.horse_id
        """
    ).fetchall()

    def filled(pred) -> int:
        return sum(1 for r in rows if pred(r))

    # Race class: heuristic from race name containing کلاس / class digits — not invented labels
    def has_class_signal(name: str | None) -> bool:
        if not name:
            return False
        return ("کلاس" in name) or ("class" in name.lower())

    # Breed proxy: surface blood hint or race surface field
    def has_breed_proxy(r) -> bool:
        surf = (r["surface"] or "").strip()
        return bool(surf)

    # Age via id_horses birth_year through links
    link = {
        int(r["warehouse_horse_id"]): int(r["horse_id"])
        for r in conn.execute(
            "SELECT warehouse_horse_id, horse_id FROM id_horse_links"
        )
    }
    birth = {
        int(r["horse_id"]): r["birth_year"]
        for r in conn.execute("SELECT horse_id, birth_year FROM id_horses")
    }

    age_filled = 0
    for r in rows:
        hid = link.get(int(r["wh_horse_id"]))
        if hid and birth.get(hid):
            age_filled += 1

    # Field size per race
    field_sizes: dict[int, int] = Counter()
    for r in rows:
        field_sizes[int(r["race_id"])] += 1
    races_with_field = sum(1 for n in field_sizes.values() if n >= 2)

    # Distance from raw_races if wh missing
    raw_dist_filled = conn.execute(
        "SELECT COUNT(*) FROM raw_races WHERE distance IS NOT NULL AND is_current=1"
    ).fetchone()[0]
    raw_races = conn.execute(
        "SELECT COUNT(*) FROM raw_races WHERE is_current=1"
    ).fetchone()[0]
    wh_dist_missing = sum(1 for r in rows if r["distance"] is None)
    # Try recover count from raw by source_race_id
    recoverable = 0
    if wh_dist_missing:
        raw_by_src = {
            str(r["source_race_id"]): r["distance"]
            for r in conn.execute(
                "SELECT source_race_id, distance FROM raw_races WHERE is_current=1 AND distance IS NOT NULL"
            )
        }
        wh_races = {
            int(r["id"]): str(r["source_race_id"])
            for r in conn.execute("SELECT id, source_race_id FROM wh_races")
        }
        seen_missing_races = {int(r["race_id"]) for r in rows if r["distance"] is None}
        for rid in seen_missing_races:
            sid = wh_races.get(rid)
            if sid and sid in raw_by_src:
                recoverable += 1

    dims = {
        "DISTANCE": {
            "unit": "result_rows",
            "total": total_results,
            "filled": filled(lambda r: r["distance"] is not None),
            "missing": filled(lambda r: r["distance"] is None),
            "coverage_pct": _pct(filled(lambda r: r["distance"] is not None), total_results),
            "raw_races_distance_filled": raw_dist_filled,
            "raw_races_total_current": raw_races,
            "wh_races_with_missing_distance": len(
                {int(r["race_id"]) for r in rows if r["distance"] is None}
            ),
            "recoverable_from_raw_source_race_id": recoverable,
            "notes": "Do not invent distance; recover only from source fields.",
        },
        "TRACK": {
            "unit": "result_rows",
            "total": total_results,
            "filled": filled(lambda r: bool(r["track"] or r["racecourse_code"])),
            "coverage_pct": _pct(
                filled(lambda r: bool(r["track"] or r["racecourse_code"])), total_results
            ),
        },
        "RACE_CLASS": {
            "unit": "result_rows",
            "total": total_results,
            "filled": filled(lambda r: has_class_signal(r["race_name"])),
            "coverage_pct": _pct(
                filled(lambda r: has_class_signal(r["race_name"])), total_results
            ),
            "notes": "Signal from race name only; unknown class left unknown (not invented).",
        },
        "BREED": {
            "unit": "result_rows",
            "total": total_results,
            "filled": filled(has_breed_proxy),
            "coverage_pct": _pct(filled(has_breed_proxy), total_results),
            "notes": "Proxy = wh_races.surface / blood hint when present; not a full breed ontology.",
        },
        "TRAINER": {
            "unit": "result_rows",
            "total": total_results,
            "filled": filled(lambda r: r["trainer_id"] is not None),
            "coverage_pct": _pct(filled(lambda r: r["trainer_id"] is not None), total_results),
        },
        "OWNER": {
            "unit": "result_rows",
            "total": total_results,
            "filled": filled(lambda r: r["owner_id"] is not None),
            "coverage_pct": _pct(filled(lambda r: r["owner_id"] is not None), total_results),
        },
        "WEIGHT": {
            "unit": "result_rows",
            "total": total_results,
            "filled": filled(lambda r: r["weight"] is not None),
            "coverage_pct": _pct(filled(lambda r: r["weight"] is not None), total_results),
        },
        "AGE_BIRTH_YEAR": {
            "unit": "result_rows",
            "total": total_results,
            "filled": age_filled,
            "coverage_pct": _pct(age_filled, total_results),
            "canonical_horses_with_birth_year": conn.execute(
                "SELECT COUNT(*) FROM id_horses WHERE birth_year IS NOT NULL"
            ).fetchone()[0],
            "canonical_horses_total": total_horses,
        },
        "FIELD_SIZE": {
            "unit": "races",
            "total": total_races,
            "filled": races_with_field,
            "coverage_pct": _pct(races_with_field, total_races),
            "notes": "Field size derived from count of wh_race_results per race_id.",
        },
    }

    return {
        "generated_at_utc": _utc_now(),
        "database": str(DB_PATH),
        "totals": {
            "wh_race_results": total_results,
            "wh_races": total_races,
            "id_horses_active": total_horses,
        },
        "dimensions": dims,
    }


def audit_anomalies(conn: sqlite3.Connection) -> dict[str, Any]:
    anomalies: list[dict[str, Any]] = []

    # finish=0
    finish0 = conn.execute(
        "SELECT COUNT(*) FROM wh_race_results WHERE finish_position = 0"
    ).fetchone()[0]
    anomalies.append(
        {
            "type": "finish_position_zero",
            "severity": "MEDIUM",
            "count": finish0,
            "action": "Do not delete; treat as non-finisher / data quirk with provenance.",
        }
    )

    # NULL finishes
    null_fin = conn.execute(
        "SELECT COUNT(*) FROM wh_race_results WHERE finish_position IS NULL"
    ).fetchone()[0]
    anomalies.append(
        {
            "type": "null_finish_position",
            "severity": "LOW",
            "count": null_fin,
            "action": "Likely scratched/DNF; retain rows.",
        }
    )

    # Impossible positions: finish > field_size or finish < 1
    bad_pos = 0
    examples: list[dict[str, Any]] = []
    field = Counter(
        int(r[0])
        for r in conn.execute("SELECT race_id FROM wh_race_results")
    )
    for r in conn.execute(
        "SELECT id, race_id, horse_id, finish_position FROM wh_race_results WHERE finish_position IS NOT NULL"
    ):
        fp = int(r["finish_position"])
        fs = field[int(r["race_id"])]
        if fp < 0 or (fp > 0 and fp > fs + 2):  # allow small tolerance for DNS quirks
            bad_pos += 1
            if len(examples) < 20:
                examples.append(
                    {
                        "result_id": r["id"],
                        "race_id": r["race_id"],
                        "wh_horse_id": r["horse_id"],
                        "finish_position": fp,
                        "field_size": fs,
                    }
                )
    anomalies.append(
        {
            "type": "impossible_finish_vs_field",
            "severity": "HIGH" if bad_pos else "OK",
            "count": bad_pos,
            "examples": examples,
            "action": "Flag only; do not delete historical results.",
        }
    )

    # Duplicate results: same race_id + horse_id
    dups = conn.execute(
        """
        SELECT race_id, horse_id, COUNT(*) AS c
        FROM wh_race_results
        GROUP BY race_id, horse_id
        HAVING c > 1
        """
    ).fetchall()
    anomalies.append(
        {
            "type": "duplicate_race_horse_results",
            "severity": "HIGH" if dups else "OK",
            "count": len(dups),
            "examples": [dict(r) for r in dups[:20]],
            "action": "Investigate; prefer versioning over silent delete.",
        }
    )

    # Date anomalies: null race_date or future far dates
    null_dates = conn.execute(
        "SELECT COUNT(*) FROM wh_races WHERE race_date IS NULL"
    ).fetchone()[0]
    future = conn.execute(
        "SELECT COUNT(*) FROM wh_races WHERE race_date > date('now', '+30 day')"
    ).fetchone()[0]
    anomalies.append(
        {
            "type": "race_date_null",
            "severity": "HIGH" if null_dates else "OK",
            "count": null_dates,
        }
    )
    anomalies.append(
        {
            "type": "race_date_far_future",
            "severity": "MEDIUM" if future else "OK",
            "count": future,
        }
    )

    # Age/birth-year anomalies: birth_year > race year or < 1980
    age_bad = []
    for r in conn.execute(
        """
        SELECT h.horse_id, h.display_name, h.birth_year, MIN(ra.race_date) AS first_race
        FROM id_horses h
        JOIN id_horse_links l ON l.horse_id = h.horse_id
        JOIN wh_race_results rr ON rr.horse_id = l.warehouse_horse_id
        JOIN wh_races ra ON ra.id = rr.race_id
        WHERE h.birth_year IS NOT NULL
        GROUP BY h.horse_id
        """
    ):
        by = int(r["birth_year"])
        fr = str(r["first_race"] or "")[:4]
        if by < 1980 or by > 2026:
            age_bad.append(
                {
                    "horse_id": r["horse_id"],
                    "horse": r["display_name"],
                    "birth_year": by,
                    "reason": "birth_year_out_of_range",
                }
            )
        elif fr.isdigit() and by > int(fr):
            age_bad.append(
                {
                    "horse_id": r["horse_id"],
                    "horse": r["display_name"],
                    "birth_year": by,
                    "first_race_year": int(fr),
                    "reason": "birth_year_after_first_race",
                }
            )
        if len(age_bad) >= 50:
            break
    # count all
    age_count = 0
    for r in conn.execute(
        """
        SELECT h.horse_id, h.birth_year, MIN(substr(ra.race_date,1,4)) AS y
        FROM id_horses h
        JOIN id_horse_links l ON l.horse_id = h.horse_id
        JOIN wh_race_results rr ON rr.horse_id = l.warehouse_horse_id
        JOIN wh_races ra ON ra.id = rr.race_id
        WHERE h.birth_year IS NOT NULL
        GROUP BY h.horse_id
        """
    ):
        by = int(r["birth_year"])
        y = r["y"]
        if by < 1980 or by > 2026 or (y and y.isdigit() and by > int(y)):
            age_count += 1
    anomalies.append(
        {
            "type": "birth_year_anomalies",
            "severity": "MEDIUM" if age_count else "OK",
            "count": age_count,
            "examples": age_bad[:20],
            "action": "Correct via provenance-preserving canonical fields (see birth_year_corrections).",
        }
    )

    # Identity conflicts: merge candidates open / multiple source ids same horse with conflicting pedigree already reported
    merge_open = conn.execute(
        "SELECT COUNT(*) FROM id_horse_merge_candidates WHERE status IS NULL OR status IN ('open','pending','candidate')"
    ).fetchone()[0]
    # fallback if status values differ
    merge_total = conn.execute("SELECT COUNT(*) FROM id_horse_merge_candidates").fetchone()[0]
    anomalies.append(
        {
            "type": "identity_merge_candidates",
            "severity": "MEDIUM",
            "open_or_pending": merge_open,
            "total": merge_total,
            "action": "Do not merge without evidence.",
        }
    )

    # Trainer/owner name collisions (same normalized name different ids) — sample
    trainer_dups = conn.execute(
        """
        SELECT name, COUNT(*) AS c FROM wh_trainers
        WHERE name IS NOT NULL AND TRIM(name) != ''
        GROUP BY name HAVING c > 1
        """
    ).fetchall()
    owner_dups = conn.execute(
        """
        SELECT name, COUNT(*) AS c FROM wh_owners
        WHERE name IS NOT NULL AND TRIM(name) != ''
        GROUP BY name HAVING c > 1 LIMIT 50
        """
    ).fetchall()
    anomalies.append(
        {
            "type": "trainer_name_duplicate_rows",
            "severity": "LOW",
            "count": len(trainer_dups),
            "examples": [dict(r) for r in trainer_dups[:10]],
            "notes": "Duplicate name rows ≠ proven same person; do not auto-merge.",
        }
    )
    anomalies.append(
        {
            "type": "owner_name_duplicate_rows",
            "severity": "LOW",
            "count": conn.execute(
                """
                SELECT COUNT(*) FROM (
                  SELECT name FROM wh_owners
                  WHERE name IS NOT NULL AND TRIM(name) != ''
                  GROUP BY name HAVING COUNT(*) > 1
                )
                """
            ).fetchone()[0],
            "examples": [dict(r) for r in owner_dups[:10]],
        }
    )

    # Pedigree conflicts from file
    ped_conflicts_path = Path(__file__).resolve().parents[2] / "data" / "pedigree" / "pedigree_conflicts.json"
    ped_n = 0
    if ped_conflicts_path.exists():
        ped_n = json.loads(ped_conflicts_path.read_text(encoding="utf-8")).get("conflict_count", 0)
    anomalies.append(
        {
            "type": "pedigree_conflicts",
            "severity": "HIGH" if ped_n else "OK",
            "count": ped_n,
            "source": str(ped_conflicts_path),
            "action": "Do not auto-resolve.",
        }
    )

    return {
        "generated_at_utc": _utc_now(),
        "anomaly_types": anomalies,
        "policy": [
            "Never delete valid historical results merely because metadata is wrong.",
            "Correct metadata only through provenance-preserving canonical fields or migration proposal.",
            "Do not invent missing class/breed/distance.",
        ],
    }


def build_dq_report(context: dict[str, Any], anomalies: dict[str, Any]) -> dict[str, Any]:
    dims = context["dimensions"]
    critical_missing = []
    for key in ("DISTANCE", "TRACK", "TRAINER", "WEIGHT", "FIELD_SIZE"):
        cov = dims[key]["coverage_pct"]
        if cov < 90:
            critical_missing.append({"dimension": key, "coverage_pct": cov})

    high = [a for a in anomalies["anomaly_types"] if a.get("severity") == "HIGH" and a.get("count", 0)]
    status = "GOOD"
    if critical_missing or high:
        status = "WARNINGS"
    if any(a.get("type") == "duplicate_race_horse_results" and a.get("count", 0) > 0 for a in anomalies["anomaly_types"]):
        status = "NEEDS_ATTENTION"

    return {
        "generated_at_utc": _utc_now(),
        "overall_status": status,
        "context_summary": {k: {"coverage_pct": v["coverage_pct"], "filled": v.get("filled"), "total": v.get("total")} for k, v in dims.items()},
        "critical_coverage_gaps": critical_missing,
        "high_severity_anomalies": high,
        "rules_enforced": [
            "No betting data",
            "No silent deletion of historical results",
            "No invented class/distance",
            "No entity merge without evidence",
        ],
        "db_modified": False,
    }


def run_phase2(db_path: Path = DB_PATH) -> dict[str, Any]:
    out = NIGHT_DIR / "phase2_data_quality"
    out.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        return {"status": "BLOCKED", "reason": f"DB missing: {db_path}"}

    conn = _conn(db_path)
    try:
        context = audit_context(conn)
        anomalies = audit_anomalies(conn)
        dq = build_dq_report(context, anomalies)
    finally:
        conn.close()

    (out / "context_coverage_report.json").write_text(
        json.dumps(context, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / "anomaly_report.json").write_text(
        json.dumps(anomalies, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / "data_quality_report.json").write_text(
        json.dumps(dq, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    md = [
        "# Phase 2 — Data Quality + Context Completion",
        "",
        f"- Generated: `{dq['generated_at_utc']}`",
        f"- Overall: **{dq['overall_status']}**",
        f"- DB modified: **no**",
        "",
        "## Context coverage",
        "",
    ]
    for k, v in context["dimensions"].items():
        md.append(f"- **{k}**: {v['coverage_pct']}% ({v.get('filled')}/{v.get('total')})")
    md += ["", "## High-severity anomalies", ""]
    if dq["high_severity_anomalies"]:
        for a in dq["high_severity_anomalies"]:
            md.append(f"- `{a['type']}` count={a.get('count')}")
    else:
        md.append("- none")
    md.append("")
    (out / "PHASE2_REPORT.md").write_text("\n".join(md), encoding="utf-8")

    return {
        "status": "COMPLETE",
        "phase": 2,
        "overall_status": dq["overall_status"],
        "output_dir": str(out),
        "critical_coverage_gaps": dq["critical_coverage_gaps"],
        "high_severity_anomaly_count": len(dq["high_severity_anomalies"]),
    }
