# Pedigree Migration Proposal

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
