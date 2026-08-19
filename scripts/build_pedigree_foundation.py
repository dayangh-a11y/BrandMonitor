#!/usr/bin/env python3
"""Pedigree Foundation builder — file outputs only; no DB mutation; no ML.

Usage:
  .venv/bin/python scripts/build_pedigree_foundation.py
  .venv/bin/python scripts/build_pedigree_foundation.py --limit 100
  .venv/bin/python scripts/build_pedigree_foundation.py --skip-harvest
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.pedigree.harvest import harvest_many, load_done_ids
from src.pedigree.report import (
    audit_local_sources,
    coverage_report,
    depth_report,
    network_report,
    quality_summary,
    write_json,
    write_jsonl,
)
from src.pedigree.resolve import build_entities_and_relationships, load_harvest, load_identity_maps

DB_DEFAULT = ROOT / "output" / "historical" / "horse_racing.db"
OUT_DEFAULT = ROOT / "data" / "pedigree"


def list_source_horse_ids(db_path: Path) -> list[str]:
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        """
        SELECT DISTINCT source_horse_id
        FROM id_horse_links
        WHERE source_horse_id IS NOT NULL AND TRIM(source_horse_id) != ''
        ORDER BY 1
        """
    ).fetchall()
    if not rows:
        rows = conn.execute(
            """
            SELECT DISTINCT source_horse_id FROM raw_horses
            WHERE is_current = 1 AND source_horse_id IS NOT NULL
            ORDER BY 1
            """
        ).fetchall()
    conn.close()
    return [str(r[0]) for r in rows]


def write_migration_proposal(path: Path) -> None:
    path.write_text(
        """# Pedigree Migration Proposal

**Status:** PROPOSAL ONLY — do not apply until reviewed.  
**ML STATUS:** `DO_NOT_TRAIN_YET`  
**DB STATUS:** no live schema changes in this phase.

## Context

Local `raw_horses.sire` / `dam` and `wh_horse_pedigree` are structurally present but
**empty**. Pedigree exists on asbdavani at:

`https://asbdavani.app/performance/horses/{source_horse_id}/pedigree`

This phase harvests that source into files. DB migration should land only after review.

## Tables required

### 1. `raw_horse_pedigree` (append-only raw)

| column | type | notes |
|--------|------|-------|
| id | INTEGER PK | |
| ingest_run_id | INTEGER FK | optional |
| source | TEXT | e.g. `asbdavani_pedigree_page` |
| source_horse_id | TEXT | subject |
| subject_name | TEXT | |
| sire_name | TEXT NULL | |
| sire_source_id | TEXT NULL | |
| dam_name | TEXT NULL | |
| dam_source_id | TEXT NULL | |
| sire_sire_name / sire_sire_source_id | TEXT NULL | grandparents |
| sire_dam_name / sire_dam_source_id | TEXT NULL | |
| dam_sire_name / dam_sire_source_id | TEXT NULL | |
| dam_dam_name / dam_dam_source_id | TEXT NULL | |
| payload_json | TEXT/JSON | full parsed chart |
| source_url | TEXT | |
| parser_version | TEXT | |
| source_hash | TEXT | |
| crawl_time / updated_time | DATETIME | |
| is_current | BOOLEAN | |
| version | INTEGER | append-only versioning |

**Unique (current):** `(source, source_horse_id)` where `is_current=1`  
**Indexes:** `source_horse_id`, `sire_source_id`, `dam_source_id`

### 2. `ped_entities` (canonical SIRE/DAM entities)

| column | type | notes |
|--------|------|-------|
| entity_id | TEXT PK | e.g. `src:{source_id}` or stable surrogate |
| role | TEXT | `SIRE` / `DAM` / `MIXED` |
| canonical_name | TEXT | |
| normalized_name | TEXT | indexed |
| sex | TEXT NULL | |
| breed | TEXT NULL | |
| birth_year | INTEGER NULL | |
| linked_horse_id | INTEGER NULL FK → id_horses | when parent also raced |
| confidence | TEXT | HIGH/MEDIUM/LOW |
| source | TEXT | |
| meta_json | JSON | raw_names, source_ids, external_urls |

**Unique:** prefer unique `source_id` when present (via link table).  
**Do not** unique on `normalized_name` alone (normalization ≠ identity).

### 3. `ped_entity_source_ids`

| column | type |
|--------|------|
| entity_id | TEXT FK |
| source | TEXT |
| source_id | TEXT |
| **UNIQUE**(source, source_id) |

### 4. `ped_horse_parents` (horse → parent relationships)

| column | type | notes |
|--------|------|-------|
| id | INTEGER PK | |
| horse_id | INTEGER FK → id_horses | |
| field | TEXT | `sire` / `dam` |
| parent_entity_id | TEXT FK → ped_entities | |
| source | TEXT | provenance |
| source_url | TEXT | |
| confidence | TEXT | HIGH/MEDIUM/LOW/MISSING |
| quality | TEXT | HIGH/MEDIUM/LOW/MISSING (data quality) |
| evidence_json | JSON | |
| is_current | BOOLEAN | |
| created_at | DATETIME | |

**Unique (current):** `(horse_id, field)` where `is_current=1` **only if no conflict**.  
Conflicts should leave relationship unset or mark `status=CONFLICT`.

### 5. `ped_conflicts`

| column | type |
|--------|------|
| id | INTEGER PK |
| horse_id | INTEGER |
| field | TEXT |
| value_a / value_b | TEXT |
| source_a / source_b | TEXT |
| entity_a / entity_b | TEXT |
| severity | TEXT |
| status | TEXT | OPEN / RESOLVED |
| resolution_notes | TEXT NULL |
| created_at | DATETIME |

### 6. Upgrade `wh_horse_pedigree`

Keep as warehouse projection:

- fill `sire_name`, `dam_name`, `sire_horse_id`, `dam_horse_id` from `ped_horse_parents`
- add `sire_entity_id`, `dam_entity_id`, `quality`, `source`, `as_of` columns
- add provenance: `evidence_json`

## Relationships

```
id_horses 1──* ped_horse_parents *──1 ped_entities
ped_entities 1──* ped_entity_source_ids
id_horses 1──* ped_conflicts
raw_horse_pedigree (source) ──ETL──> ped_* (entity layer)
```

## Indexes / constraints summary

- `ped_horse_parents(horse_id, field, is_current)`
- `ped_horse_parents(parent_entity_id)`
- `ped_entities(normalized_name)`
- `ped_entity_source_ids(source, source_id)` UNIQUE
- **No** automatic unique merge on similar names

## Provenance fields (required)

Every relationship row must retain: `source`, `source_url`, `confidence`, `evidence_json`.

## Explicit non-goals for migration v1

- No ML features
- No automatic conflict resolution for HIGH severity
- No inventing parents from name/owner/trainer/performance
- As-of offspring stats for prediction = later phase (compute layer, not static table)

## Rollout plan

1. Review this proposal + `data/pedigree/*` artifacts
2. Add tables via Alembic / schema migrate (append-only raw first)
3. Load from `pedigree_harvest.jsonl` + `pedigree_relationships.jsonl`
4. Backfill `wh_horse_pedigree` + `id_horses.sire_normalized/dam_normalized`
5. Gate ML until pedigree quality gates are accepted
""",
        encoding="utf-8",
    )


def write_foundation_report(path: Path, payload: dict) -> None:
    q = payload["final_questions"]
    cov = payload["coverage"]
    lines = [
        "# PEDIGREE FOUNDATION REPORT",
        "",
        f"- Generated (UTC): `{payload['generated_at_utc']}`",
        f"- ML STATUS: **`DO_NOT_TRAIN_YET`**",
        f"- DB writes: **none** (files + migration proposal only)",
        "",
        "## Verdict",
        "",
        payload["verdict"],
        "",
        "## Final questions",
        "",
        f"1. Does existing raw/source data contain sire information? **{q['q1_sire_in_existing_raw']}**",
        f"2. Does it contain dam information? **{q['q2_dam_in_existing_raw']}**",
        f"3. What percentage of horses have sire? **{q['q3_sire_pct']}%**",
        f"4. What percentage have dam? **{q['q4_dam_pct']}%**",
        f"5. What percentage have both? **{q['q5_both_pct']}%**",
        f"6. How many unique sire entities can be resolved? **{q['q6_sire_entities']}**",
        f"7. How many unique dam entities can be resolved? **{q['q7_dam_entities']}**",
        f"8. How many pedigree conflicts exist? **{q['q8_conflicts']}**",
        f"9. What is the maximum reliable pedigree depth? **{q['q9_max_depth']}**",
        f"10. Is pedigree data good enough to become a prediction feature later? **{q['q10_feature_ready']}**",
        "",
        "## Coverage (canonical horses)",
        "",
        f"- Total canonical horses: {cov['total_canonical_horses']}",
        f"- With sire: {cov['horses_with_sire']} ({cov['sire_coverage_pct']}%)",
        f"- With dam: {cov['horses_with_dam']} ({cov['dam_coverage_pct']}%)",
        f"- With both: {cov['horses_with_both']} ({cov['complete_pedigree_coverage_pct']}%)",
        f"- With neither: {cov['horses_with_neither']}",
        "",
        "## Harvest",
        "",
        f"- Harvest rows: {payload['harvest_stats']}",
        "",
        "## Quality",
        "",
        "```json",
        json.dumps(payload["quality"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Artifacts",
        "",
    ]
    for name in payload["artifacts"]:
        lines.append(f"- `{name}`")
    lines += [
        "",
        "## Rules enforced",
        "",
        "- No invented pedigree from name/owner/trainer/age/performance",
        "- Normalization ≠ identity merge",
        "- Conflicts reported, not auto-resolved",
        "- Offspring network stats are STATIC DESCRIPTIVE (not as-of; not for prediction yet)",
        "",
        "## Next steps",
        "",
        "1. Review `pedigree_migration_proposal.md`",
        "2. After approval, load harvest into `raw_horse_pedigree` + entity tables",
        "3. Optionally deepen pedigree by following parent `/pedigree` pages (depth 3+)",
        "4. Keep ML gated (`DO_NOT_TRAIN_YET`)",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=DB_DEFAULT)
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=None, help="Limit harvest count (resume-aware)")
    ap.add_argument("--skip-harvest", action="store_true")
    args = ap.parse_args()

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    harvest_path = out / "pedigree_harvest.jsonl"

    # 1) Local source audit (always)
    audit = audit_local_sources(args.db)
    write_json(out / "pedigree_source_audit.json", audit)

    # 2) Harvest live pedigree pages into files
    source_ids = list_source_horse_ids(args.db)
    harvest_stats: dict = {
        "unique_source_horse_ids": len(source_ids),
        "skipped": bool(args.skip_harvest),
    }
    if not args.skip_harvest:
        stats = harvest_many(
            source_ids,
            harvest_path,
            workers=args.workers,
            limit=args.limit,
        )
        harvest_stats.update(stats)
    else:
        harvest_stats["already_done"] = len(load_done_ids(harvest_path))

    write_json(out / "pedigree_harvest_stats.json", harvest_stats)

    if not harvest_path.exists():
        # Still emit empty foundation artifacts
        harvest: list[dict] = []
    else:
        harvest = load_harvest(harvest_path)

    identity = load_identity_maps(args.db)
    built = build_entities_and_relationships(harvest, identity)

    write_json(out / "pedigree_entities.json", {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "entity_count": len(built["entities"]),
        "sire_entities": sum(1 for e in built["entities"] if "SIRE" in e["role_hints"]),
        "dam_entities": sum(1 for e in built["entities"] if "DAM" in e["role_hints"]),
        "entities": built["entities"],
    })
    write_jsonl(out / "pedigree_relationships.jsonl", built["relationships"])
    write_json(out / "pedigree_conflicts.json", {
        "conflict_count": len(built["conflicts"]),
        "conflicts": built["conflicts"],
    })

    cov = coverage_report(
        horses=identity["horses"],
        horse_parents=built["horse_parents"],
        harvest=harvest,
        identity=identity,
        db_path=args.db,
    )
    write_json(out / "pedigree_coverage.json", cov)

    depth = depth_report(harvest, identity["source_to_horse"])
    net = network_report(
        entities=built["entities"],
        relationships=built["relationships"],
        starts=identity["starts"],
        horses=identity["horses"],
    )
    quality = quality_summary(built["relationships"], built["conflicts"])
    write_json(
        out / "pedigree_network_report.json",
        {
            "depth": depth,
            "network": net,
            "quality": quality,
        },
    )

    write_migration_proposal(out / "pedigree_migration_proposal.md")

    # Pre-harvest local emptiness
    local_sire = next(
        s for s in audit["sources"] if s["source"] == "raw_horses" and s["field"] == "sire"
    )
    local_dam = next(
        s for s in audit["sources"] if s["source"] == "raw_horses" and s["field"] == "dam"
    )

    sire_ents = sum(1 for e in built["entities"] if "SIRE" in e["role_hints"])
    dam_ents = sum(1 for e in built["entities"] if "DAM" in e["role_hints"])

    feature_ready = (
        "CONDITIONAL_YES"
        if cov["complete_pedigree_coverage_pct"] >= 50
        and len(built["conflicts"]) < max(50, 0.01 * cov["total_canonical_horses"])
        else "NOT_YET"
    )
    if cov["complete_pedigree_coverage_pct"] >= 50:
        feature_ready_msg = (
            f"{feature_ready} — coverage supports later feature engineering after DB load + "
            "as-of offspring stats; still DO_NOT_TRAIN_YET"
        )
    else:
        feature_ready_msg = (
            f"{feature_ready} — finish harvest/load and raise complete pedigree coverage first"
        )

    final_questions = {
        "q1_sire_in_existing_raw": (
            f"NO in local DB columns (filled={local_sire['filled']}/{local_sire['number_of_records']}); "
            "YES on live asbdavani /pedigree pages (harvested into files)"
            if harvest
            else f"NO in local DB (filled={local_sire['filled']}); live /pedigree source exists but harvest empty"
        ),
        "q2_dam_in_existing_raw": (
            f"NO in local DB columns (filled={local_dam['filled']}/{local_dam['number_of_records']}); "
            "YES on live asbdavani /pedigree pages (harvested into files)"
            if harvest
            else f"NO in local DB (filled={local_dam['filled']}); live /pedigree source exists but harvest empty"
        ),
        "q3_sire_pct": cov["sire_coverage_pct"],
        "q4_dam_pct": cov["dam_coverage_pct"],
        "q5_both_pct": cov["complete_pedigree_coverage_pct"],
        "q6_sire_entities": sire_ents,
        "q7_dam_entities": dam_ents,
        "q8_conflicts": len(built["conflicts"]),
        "q9_max_depth": (
            "2 from a single subject chart; 3+ only by following parent pedigree pages "
            "(not invented)"
        ),
        "q10_feature_ready": feature_ready_msg,
    }

    chart_sire = sum(1 for r in harvest if r.get("sire"))
    chart_dam = sum(1 for r in harvest if r.get("dam"))
    verdict = (
        "Local entity-layer pedigree was empty (SIRE=0/DAM=0) because race-card/history "
        "ingest never captured parents. Live asbdavani `/pedigree` pages DO contain sire/dam "
        f"charts; this phase harvested {len(harvest)} pages "
        f"(chart sire={chart_sire}, chart dam={chart_dam}) into files without DB mutation."
    )

    artifacts = [
        "data/pedigree/pedigree_source_audit.json",
        "data/pedigree/pedigree_harvest.jsonl",
        "data/pedigree/pedigree_entities.json",
        "data/pedigree/pedigree_relationships.jsonl",
        "data/pedigree/pedigree_conflicts.json",
        "data/pedigree/pedigree_coverage.json",
        "data/pedigree/pedigree_network_report.json",
        "data/pedigree/pedigree_migration_proposal.md",
        "data/pedigree/PEDIGREE_FOUNDATION_REPORT.md",
    ]
    report_payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "final_questions": final_questions,
        "coverage": cov,
        "harvest_stats": harvest_stats,
        "quality": quality,
        "artifacts": artifacts,
        "ml_status": "DO_NOT_TRAIN_YET",
    }
    write_json(out / "pedigree_foundation_summary.json", report_payload)
    write_foundation_report(out / "PEDIGREE_FOUNDATION_REPORT.md", report_payload)

    print(json.dumps({
        "harvest_stats": harvest_stats,
        "entities": len(built["entities"]),
        "relationships": len(built["relationships"]),
        "conflicts": len(built["conflicts"]),
        "coverage": {
            "sire_pct": cov["sire_coverage_pct"],
            "dam_pct": cov["dam_coverage_pct"],
            "both_pct": cov["complete_pedigree_coverage_pct"],
        },
        "out": str(out),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
