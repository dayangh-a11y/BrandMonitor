# Data Platform Architecture (Sprint 2)

Production-grade layers for a horse racing analytics platform.

**Collector is frozen** — this document covers infrastructure above collection.

## Layers

| Package | Prefix | Role |
|---------|--------|------|
| `src/raw/` | `raw_*` | Exact website extracts (append-only versions) |
| `src/warehouse/` | `wh_*` | Normalized curated entities |
| `src/features/` | `feat_*_features` | Empty recalculable feature shells |
| `src/quality/` | `quality_*` | Validation pipeline + reports |
| `src/versioning/` | mixin fields | `source_url`, `parser_version`, `crawl_time`, `updated_time`, `source_hash` |
| `src/crawler/` | `crawl_*` | Queue, resume, retry, dedupe, progress |

```
Datasource → Collector (JSON)
                ↓ --persist
              raw_*  (append-only history)
                ↓ warehouse build
              wh_*   (Horses, Races, RaceResults, Jockeys, Trainers, Owners, RaceVideos, HorsePedigree)
                ↓ features recalc
              feat_*_features (empty shells — fill later)
                ↓ quality-report
              quality_* issues + CLI report
```

## RAW (never overwrite)

- Store extracted values only (type conversion allowed).
- No derived features, no analytics cleaning.
- On re-import: if `source_hash` unchanged → skip; if changed → insert new `version`, set prior `is_current=false`.
- Every row carries versioning fields from `src/versioning`.

## WAREHOUSE

Normalized tables:

- `wh_horses`, `wh_races`, `wh_race_results`
- `wh_jockeys`, `wh_trainers`, `wh_owners`
- `wh_race_videos`
- `wh_horse_pedigree` (structure only — no pedigree analysis)
- `wh_entity_matches` (duplicate candidates)

Build: `python main.py warehouse build`

## FEATURES

Empty shells:

- `feat_horse_features` (HorseFeatures)
- `feat_race_features` (RaceFeatures)
- `feat_trainer_features` (TrainerFeatures)
- `feat_jockey_features` (JockeyFeatures)

Recalculate anytime: `python main.py features recalc`  
Features are **never** written into Raw.

## Entity resolution

Fuzzy + exact-normalized matching for horses / jockeys / trainers / owners  
(`src/warehouse/fuzzy.py`, `src/warehouse/entities.py`).

## Data quality

Checks: missing values, duplicates, invalid dates/ratings/times, broken links, parser errors.

```bash
python main.py quality-report
```

## Crawler manager

```bash
python main.py crawler enqueue --url "..." --type race
python main.py crawler progress
python main.py crawler resume
```

Supports resume, retry, duplicate prevention, progress tracking, queue processing.

## Out of scope (this sprint)

Machine Learning · Prediction · Video Analysis · Pedigree Analysis · Statistics
