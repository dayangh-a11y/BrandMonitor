# Horse Identity Resolution Engine

**Problem:** horse matching by exact name is unreliable (Persian spelling variants,
zero-width characters, Arabic vs Persian letters, duplicates across source IDs).

**Rule:** never rely on exact string matching. Every horse gets one permanent
`horse_id`. Future lookups use `horse_id`, not `horse_name`.

## Signals

Matching combines:

| Signal | Role |
|--------|------|
| Normalized Persian name | ZW strip, Arabic→Persian letters, spaces, fuzzy |
| Sire | Pedigree / payload when present |
| Dam | Pedigree / payload when present |
| Age | Birthdate or observed card age |
| Sex | نر / ماده / اخته normalized |
| Owner | Frequency from race results |
| Trainer | Frequency from race results |
| Source horse id | Strong link when available (not a name) |

## Tables

- `id_horses` — permanent `horse_id`
- `id_horse_links` — `wh_horses.id` → `horse_id` (many:1)
- `id_horse_aliases` — normalized aliases
- `id_horse_merge_candidates` — open duplicate / merge review queue
- `id_horse_build_runs` — build audit

`wh_horses.canonical_entity_id` is set to the permanent `horse_id` on build.

## CLI

```bash
python main.py identity build
python main.py identity report
python main.py identity report --json
python main.py identity resolve --name "تریموف" --sex نر --owner "..." --trainer "..."
python main.py identity resolve --name "هج لایک" --sire "استراث برن" --dam "بالاهج" --age 3
```

## API

```python
from src.identity import HorseQuery, resolve_horse_id, build_horse_identity

horse_id = resolve_horse_id(
    session,
    name="پرنس آف اسپید",
    sire="وان من باند",
    dam="سرخان هج",
    age=3,
    sex="نر",
    owner="باشگاه اسب صدر",
    trainer="محمد اعظمی",
)
```

## Thresholds

- Auto-merge ≥ 0.88 (with name similarity ≥ 0.80)
- Candidate (report) ≥ 0.72
- Lookup accept ≥ 0.70

Sex hard-conflicts and very weak name scores suppress merges.

## Canonical attribute corrections

`id_horses.birth_year` is the **canonical** derived field. Raw source values in
`raw_horses` / `wh_horses.birthdate` are never overwritten.

Durable corrections live in `data/identity/birth_year_corrections.json` and are
re-applied after identity builds via `src/identity/corrections.py`.

Provenance is stored on the horse as `meta_json.birth_year_correction`:

- `source` (e.g. `inferred_from_race_age_sequence`)
- `confidence`
- `evidence`
- `old_value` / `new_value`

Apply:

```bash
python scripts/apply_birth_year_correction_1771.py
python scripts/apply_birth_year_correction_1771.py --dry-run
```

## Package

`src/identity/` — `normalize`, `score`, `load`, `build`, `resolve`, `report`, `models`, `corrections`
