# PEDIGREE FOUNDATION REPORT

- Generated (UTC): `2026-08-08T18:47:44.750754+00:00`
- ML STATUS: **`DO_NOT_TRAIN_YET`**
- DB writes: **none** (files + migration proposal only)

## Verdict

Local entity-layer pedigree was empty (SIRE=0/DAM=0) because race-card/history ingest never captured parents. Live asbdavani `/pedigree` pages DO contain sire/dam charts; this phase harvested 9428 pages (chart sire=9391, chart dam=9128) into files without DB mutation.

## Final questions

1. Does existing raw/source data contain sire information? **NO in local DB columns (filled=0/33117); YES on live asbdavani /pedigree pages (harvested into files)**
2. Does it contain dam information? **NO in local DB columns (filled=0/33117); YES on live asbdavani /pedigree pages (harvested into files)**
3. What percentage of horses have sire? **99.522%**
4. What percentage have dam? **96.6964%**
5. What percentage have both? **96.5158%**
6. How many unique sire entities can be resolved? **1251**
7. How many unique dam entities can be resolved? **5145**
8. How many pedigree conflicts exist? **19**
9. What is the maximum reliable pedigree depth? **2 from a single subject chart; 3+ only by following parent pedigree pages (not invented)**
10. Is pedigree data good enough to become a prediction feature later? **CONDITIONAL_YES — coverage supports later feature engineering after DB load + as-of offspring stats; still DO_NOT_TRAIN_YET**

## Coverage (canonical horses)

- Total canonical horses: 9414
- With sire: 9369 (99.522%)
- With dam: 9103 (96.6964%)
- With both: 9086 (96.5158%)
- With neither: 28

## Pedigree depth (subject charts)

- Depth 0: 20
- Depth 1: 2580
- Depth 2: 6828
- Max reliable from one page: **2** (grandparents). Depth 3+ requires following parent `/pedigree` pages.

## Harvest

- Unique source horse ids harvested: **9428**
- Chart parse OK: 9408; empty charts: 20; fetch errors after retry: 0

## Quality

```json
{
  "relationship_quality_counts": {
    "HIGH": 18472
  },
  "horses_with_conflicts": 11,
  "scale": [
    "HIGH",
    "MEDIUM",
    "LOW",
    "MISSING"
  ],
  "definition": {
    "HIGH": "Source pedigree page + parent source_id + no conflict",
    "MEDIUM": "Named parent without stable source_id (or external-only link)",
    "LOW": "Conflict present or weak evidence",
    "MISSING": "No source pedigree parent"
  },
  "note": "DATA QUALITY indicator — NOT a prediction probability."
}
```

## Artifacts

- `data/pedigree/pedigree_source_audit.json`
- `data/pedigree/pedigree_harvest.jsonl`
- `data/pedigree/pedigree_entities.json`
- `data/pedigree/pedigree_relationships.jsonl`
- `data/pedigree/pedigree_conflicts.json`
- `data/pedigree/pedigree_coverage.json`
- `data/pedigree/pedigree_network_report.json`
- `data/pedigree/pedigree_migration_proposal.md`
- `data/pedigree/PEDIGREE_FOUNDATION_REPORT.md`

## Rules enforced

- No invented pedigree from name/owner/trainer/age/performance
- Normalization ≠ identity merge
- Conflicts reported, not auto-resolved
- Offspring network stats are STATIC DESCRIPTIVE (not as-of; not for prediction yet)

## Next steps

1. Review `pedigree_migration_proposal.md`
2. After approval, load harvest into `raw_horse_pedigree` + entity tables
3. Optionally deepen pedigree by following parent `/pedigree` pages (depth 3+)
4. Keep ML gated (`DO_NOT_TRAIN_YET`)
