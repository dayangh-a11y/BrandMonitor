# Coverage-First Phase (Priority Lock)

**Enrichment is blocked** until historical RaceDay / Heat / Result coverage reaches the gate.

Blocked until gate opens: pedigree, age/birthdate, weather, features, video analytics.

## Phase-1 core payload (every heat)

- Race Day (date + track)
- Heat (round, breed/surface, distance)
- Results (finish, horse, trainer, owner)
- Dual dates: `race_date` (Gregorian, internal) + `race_date_jalali` (Shamsi, display)
- Provenance: `source`, `source_url`, `extracted_at` / `crawl_time`

## Calendar policy

- Display default: Jalali (Asia/Tehran context)
- Query/storage internal: Gregorian
- Empty DB ranges are **Missing Coverage / UNRESOLVED**, not “no racing” and not automatic Missing Data

## Coverage Matrix (authoritative)

Structure: **Jalali year × Jalali month × city** for every known track in the DB span.

Cell classes (evidence only — empty alone is never No-Race):

- `CONFIRMED_RACE` — ≥1 heat in `wh_races` (+ race days, heats, results, breeds, source, URLs)
- `CONFIRMED_NO_RACE` — future month or gap `confirmed_no_race` (+ absence evidence)
- `MISSING_DATA` — external proof races occurred, warehouse still empty (+ proving source/URL/confidence)
- `UNRESOLVED` — empty, no proof of race or absence (+ reason)

**Product Coverage (proven race-obligation only):**

```text
Coverage = CONFIRMED_RACE / (CONFIRMED_RACE + MISSING_DATA)
```

- UNRESOLVED excluded (existence/absence not proven).
- CONFIRMED_NO_RACE excluded from Coverage debt (proven absence ≠ Missing Data).

Companion: grid-fill on deduped calendar universe, Month, City-Month, Heat→Result, Source Index, Gap Resolution.

Deprecated: `clamp(45 − gaps×0.01)` (~31.72%) and mixed `(months+city_months)/(…)`.

```bash
python scripts/build_coverage_matrix.py
python scripts/compute_coverage.py
```

## ETL

`Extract → Normalize → Validate → Deduplicate → Match Identity → Merge → Integrity Check`

- Append-only Raw (no delete/overwrite of prior versions)
- Cross-source disagreements → `cov_source_conflicts` + `cov_source_priorities`
- Gaps → `cov_missing_gaps`

## Gate

`cov_enrichment_gates.name='secondary'` — `allowed` stays false until:

1. Product Coverage ≥ `min_coverage_pct` (default 70), **and**
2. Open `MISSING_DATA` cells = 0

Blocked until gate opens: pedigree, age/birthdate, weather, features, video analytics, ranking, prediction.
