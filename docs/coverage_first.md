# Coverage-First Phase (Priority Lock)

**Hierarchy lock:** Race Week → Race Day → Heat → Result. A Heat is never a Race Day.
See `docs/hierarchy/DATA_MODEL.md`. Prior Race=Heat coverage figures are **INVALID**.

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
- Empty DB ranges are **Missing Coverage**, not “no racing”

## ETL

`Extract → Normalize → Validate → Deduplicate → Match Identity → Merge → Integrity Check`

- Append-only Raw (no delete/overwrite of prior versions)
- Cross-source disagreements → `cov_source_conflicts` + `cov_source_priorities`
- Gaps → `cov_missing_gaps`

## Commands

```bash
export DATABASE_URL=sqlite:///output/historical/horse_racing.db
export CRAWL_ALLOWED_RACECOURSES=*
python scripts/coverage_phase1.py
```

## Gate

`cov_enrichment_gates.name='secondary'` — `allowed` stays false until `current_coverage_pct >= min_coverage_pct` (default 70).

### Coverage metric (standard)

**Primary = Calendar Cell Coverage**

```text
Coverage = (filled_jalali_months + filled_city_months)
         / (eligible_jalali_months + eligible_city_months)
```

- Eligible months exclude Confirmed No-Race / future Jalali months.
- City-month cells are counted only inside months that already have ≥1 nationwide heat.
- Companion metrics: month coverage, city-month coverage, heat→result completeness, known asbdavani index coverage.
- The old `clamp(45 − gaps×0.01, 8, 55)` figure (~31.72%) was a **deprecated heuristic**, not real coverage.

```bash
python scripts/compute_coverage.py
```
