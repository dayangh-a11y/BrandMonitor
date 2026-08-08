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

## Coverage metrics (standard)

Primary universe (deduped — no month+city double count):

- Months with nationwide heats → one **city-month** cell per known track
- Empty eligible months → one **nationwide month** cell
- Exclude `CONFIRMED_NO_RACE` / future months

Cell classes (evidence only):

- `CONFIRMED_RACE` — ≥1 heat in `wh_races`
- `CONFIRMED_NO_RACE` — future month or gap `confirmed_no_race`
- `MISSING_DATA` — gap `confirmed_missing_data` (external proof, DB empty)
- `UNRESOLVED` — empty, no proof of race or absence

**Primary Coverage (grid fill):**

```text
CONFIRMED_RACE / (CONFIRMED_RACE + MISSING_DATA + UNRESOLVED)
```

**Proven obligation coverage (companion):**

```text
CONFIRMED_RACE / (CONFIRMED_RACE + MISSING_DATA)
```

Companion metrics: Month, City-Month, Heat→Result Completeness, Known Source Index, Missing-Gap Resolution.

Deprecated: `clamp(45 − gaps×0.01)` (~31.72%) and mixed `(months+city_months)/(…)`.

```bash
python scripts/compute_coverage.py
```

## ETL

`Extract → Normalize → Validate → Deduplicate → Match Identity → Merge → Integrity Check`

- Append-only Raw (no delete/overwrite of prior versions)
- Cross-source disagreements → `cov_source_conflicts` + `cov_source_priorities`
- Gaps → `cov_missing_gaps`

## Gate

`cov_enrichment_gates.name='secondary'` — `allowed` stays false until primary coverage ≥ `min_coverage_pct` (default 70).
