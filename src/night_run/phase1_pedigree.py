"""Phase 1 — package/validate pedigree foundation for Night Run."""

from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from src.night_run.paths import NIGHT_DIR, PEDIGREE_DIR


REQUIRED = [
    "pedigree_source_audit.json",
    "pedigree_entities.json",
    "pedigree_relationships.jsonl",
    "pedigree_conflicts.json",
    "pedigree_coverage.json",
    "pedigree_network_report.json",
    "pedigree_migration_proposal.md",
    "PEDIGREE_FOUNDATION_REPORT.md",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def adapt_relationships(src: Path, dst: Path) -> dict[str, Any]:
    """Ensure relationships expose parent_id/parent_type/as_of_date."""
    n = 0
    with src.open(encoding="utf-8") as fin, dst.open("w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            field = row.get("field") or ("sire" if row.get("sire_id") else "dam")
            parent_id = row.get("parent_entity_id") or row.get("sire_id") or row.get("dam_id")
            adapted = {
                "horse_id": row.get("horse_id"),
                "parent_id": parent_id,
                "parent_type": "SIRE" if field == "sire" else "DAM",
                "parent_name": row.get("parent_name"),
                "confidence": row.get("confidence"),
                "data_quality": row.get("quality") or row.get("confidence"),
                "source": row.get("source"),
                "evidence": row.get("evidence") or {},
                "as_of_date": date.today().isoformat(),
                "timestamp_utc": _utc_now(),
                # retain originals for provenance
                "legacy": {
                    k: row.get(k)
                    for k in (
                        "sire_id",
                        "dam_id",
                        "field",
                        "parent_entity_id",
                        "horse",
                        "quality",
                    )
                    if k in row
                },
            }
            fout.write(json.dumps(adapted, ensure_ascii=False) + "\n")
            n += 1
    return {"relationship_rows": n}


def run_phase1() -> dict[str, Any]:
    out = NIGHT_DIR / "phase1_pedigree"
    out.mkdir(parents=True, exist_ok=True)
    missing = [f for f in REQUIRED if not (PEDIGREE_DIR / f).exists()]
    if missing:
        return {
            "status": "BLOCKED",
            "missing": missing,
            "message": "Pedigree foundation artifacts missing — run build_pedigree_foundation.py",
        }

    copied: list[str] = []
    for name in REQUIRED:
        if name == "pedigree_relationships.jsonl":
            continue
        shutil.copy2(PEDIGREE_DIR / name, out / name)
        copied.append(name)

    rel_stats = adapt_relationships(
        PEDIGREE_DIR / "pedigree_relationships.jsonl",
        out / "pedigree_relationships.jsonl",
    )
    # also keep raw legacy copy
    shutil.copy2(
        PEDIGREE_DIR / "pedigree_relationships.jsonl",
        out / "pedigree_relationships_legacy.jsonl",
    )

    cov = json.loads((PEDIGREE_DIR / "pedigree_coverage.json").read_text(encoding="utf-8"))
    conflicts = json.loads((PEDIGREE_DIR / "pedigree_conflicts.json").read_text(encoding="utf-8"))
    ents = json.loads((PEDIGREE_DIR / "pedigree_entities.json").read_text(encoding="utf-8"))

    summary = {
        "status": "COMPLETE",
        "phase": 1,
        "generated_at_utc": _utc_now(),
        "source_dir": str(PEDIGREE_DIR),
        "output_dir": str(out),
        "copied": copied,
        "relationships": rel_stats,
        "coverage": {
            "total_canonical_horses": cov.get("total_canonical_horses"),
            "sire_coverage_pct": cov.get("sire_coverage_pct"),
            "dam_coverage_pct": cov.get("dam_coverage_pct"),
            "complete_pedigree_coverage_pct": cov.get("complete_pedigree_coverage_pct"),
        },
        "entities": {
            "total": ents.get("entity_count"),
            "sire": ents.get("sire_entities"),
            "dam": ents.get("dam_entities"),
        },
        "conflicts": conflicts.get("conflict_count"),
        "db_modified": False,
        "ml_status": "DO_NOT_TRAIN",
        "notes": [
            "Local DB pedigree columns remain empty; harvest is file-first.",
            "Normalization ≠ identity merge; conflicts not auto-resolved.",
            "Offspring network stats are static descriptive, not as-of.",
        ],
    }
    (out / "phase1_status.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary
