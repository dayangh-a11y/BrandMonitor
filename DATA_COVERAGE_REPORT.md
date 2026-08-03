# DATA_COVERAGE_REPORT

**Goal:** improve dataset coverage and confidence first; `postal_score_v1` unchanged.

**Generated from:** Maps warehouses + `data/coverage_expand/*` + official website harvest.

## Executive totals

| Metric | Value |
|--------|------:|
| Companies | 6 |
| Branches (deduped) | 425 |
| Reviews | 4292 |
| Avg overall dataset confidence | 0.448 |

Targets used for confidence: reviews≥100 full, branches≥200, cities≥100, provinces≥31.
Statistical minimum for review metrics: **n≥30** (strong: n≥100).

## Per-company coverage

| Company | Branches | Cities | Provinces | Reviews | Prov coverage % | Official completeness | Overall dataset confidence | Stats-ready (reviews≥30) |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|
| Tipax | 373 | 42 | 29 | 3732 | 93.55 | 0.636 | 0.878 | yes |
| Chapar | 19 | 7 | 8 | 244 | 25.81 | 0.727 | 0.528 | yes |
| Post | 8 | 2 | 2 | 110 | 6.45 | 0 | 0.372 | yes |
| Mahex | 17 | 4 | 7 | 120 | 22.58 | 0.455 | 0.477 | yes |
| AloPeyk | 8 | 3 | 4 | 86 | 12.9 | 0.364 | 0.388 | yes |
| Pishro | 0 | 0 | 0 | 0 | 0.0 | 0 | 0.042 | no |

## Number of branches / cities / provinces / reviews

### Tipax

- Branches covered: **373**
- Cities: **42**
- Provinces: **29** (93.55% of 31)
- Reviews: **3732**
- Coverage vs branch target (200): **100.0%**
- Sources: analytics_demo.db, postal_intelligence.db, tipax_iran.db

Metric confidence:

| Metric | Value | Confidence |
|--------|------:|-----------:|
| reviews | 3732 | 1.0 |
| branches | 373 | 1.0 |
| cities | 42 | 0.42 |
| provinces | 29 | 0.935 |
| official_profile | 0.636 | 0.636 |
| overall | — | 0.878 |

### Chapar

- Branches covered: **19**
- Cities: **7**
- Provinces: **8** (25.81% of 31)
- Reviews: **244**
- Coverage vs branch target (200): **9.5%**
- Sources: analytics_demo.db, phase11_multisource.db, postal_intelligence.db

Metric confidence:

| Metric | Value | Confidence |
|--------|------:|-----------:|
| reviews | 244 | 1.0 |
| branches | 19 | 0.095 |
| cities | 7 | 0.07 |
| provinces | 8 | 0.258 |
| official_profile | 0.727 | 0.727 |
| overall | — | 0.528 |

### Post

- Branches covered: **8**
- Cities: **2**
- Provinces: **2** (6.45% of 31)
- Reviews: **110**
- Coverage vs branch target (200): **4.0%**
- Sources: phase11_multisource.db, postal_intelligence.db

Metric confidence:

| Metric | Value | Confidence |
|--------|------:|-----------:|
| reviews | 110 | 1.0 |
| branches | 8 | 0.04 |
| cities | 2 | 0.02 |
| provinces | 2 | 0.065 |
| official_profile | 0.0 | 0.0 |
| overall | — | 0.372 |

### Mahex

- Branches covered: **17**
- Cities: **4**
- Provinces: **7** (22.58% of 31)
- Reviews: **120**
- Coverage vs branch target (200): **8.5%**
- Sources: phase11_multisource.db, postal_intelligence.db

Metric confidence:

| Metric | Value | Confidence |
|--------|------:|-----------:|
| reviews | 120 | 1.0 |
| branches | 17 | 0.085 |
| cities | 4 | 0.04 |
| provinces | 7 | 0.226 |
| official_profile | 0.455 | 0.455 |
| overall | — | 0.477 |

### AloPeyk

- Branches covered: **8**
- Cities: **3**
- Provinces: **4** (12.9% of 31)
- Reviews: **86**
- Coverage vs branch target (200): **4.0%**
- Sources: phase11_multisource.db, postal_intelligence.db

Metric confidence:

| Metric | Value | Confidence |
|--------|------:|-----------:|
| reviews | 86 | 0.86 |
| branches | 8 | 0.04 |
| cities | 3 | 0.03 |
| provinces | 4 | 0.129 |
| official_profile | 0.364 | 0.364 |
| overall | — | 0.388 |

### Pishro

- Branches covered: **0**
- Cities: **0**
- Provinces: **0** (0.0% of 31)
- Reviews: **0**
- Coverage vs branch target (200): **0.0%**
- Sources: none

Metric confidence:

| Metric | Value | Confidence |
|--------|------:|-----------:|
| reviews | 0 | 0.05 |
| branches | 0 | 0.05 |
| cities | 0 | 0.05 |
| provinces | 0 | 0.05 |
| official_profile | 0.0 | 0.0 |
| overall | — | 0.042 |

## Missing official information (website harvest)

Harvested from official domains only (`tipaxco.com`, `chaparnet.com`, `mahex.com`, `alopeyk.com`, `pishro.net`, `post.ir`).

### Tipax

- Site reachable: **yes** (12 pages OK)
- Completeness ratio: **0.636**
- Missing / not extractable from static HTML: coverage, official_pricing, weight_limits, size_limits
- Services evidenced on site: domestic_express, same_day, international, cod, insurance, packaging, tracking, pickup, door_to_door, branch_to_branch
- Support channels found: phones=['00008457', '021-41036000', '021-92008457'] emails=['CS-Support@tipax.ir', 'info@tipax.ir']

### Chapar

- Site reachable: **yes** (12 pages OK)
- Completeness ratio: **0.727**
- Missing / not extractable from static HTML: coverage, weight_limits, size_limits
- Services evidenced on site: domestic_express, same_day, international, cod, insurance, packaging, tracking, pickup, door_to_door, branch_to_branch
- Support channels found: phones=['+989046218651', '+989120578019', '021-64085', '02164085'] emails=['info@chaparnet.com']

### Post

- Site reachable: **no** ({'home': 'URLError: <urlopen error [Errno 104] Connection reset by peer>', 'www': 'URLError: <urlopen error [Errno 104] Connection reset by peer>'})
- Completeness ratio: **0**
- Missing / not extractable from static HTML: branches, services, coverage, official_delivery_times, official_pricing, weight_limits, size_limits, insurance, tracking, working_hours, customer_support

### Mahex

- Site reachable: **yes** (10 pages OK)
- Completeness ratio: **0.455**
- Missing / not extractable from static HTML: coverage, official_delivery_times, official_pricing, weight_limits, size_limits, working_hours
- Services evidenced on site: domestic_express, same_day, international, cod, insurance, packaging, tracking, pickup, door_to_door, branch_to_branch
- Support channels found: phones=[] emails=['info@mahex.com']

### AloPeyk

- Site reachable: **yes** (6 pages OK)
- Completeness ratio: **0.364**
- Missing / not extractable from static HTML: branches, coverage, official_delivery_times, official_pricing, weight_limits, size_limits, working_hours
- Services evidenced on site: domestic_express, same_day, international, insurance, packaging, tracking, pickup, urban_ondemand
- Support channels found: phones=[] emails=['support@alopeyk.com']

### Pishro

- Site reachable: **yes** (1 pages OK)
- Completeness ratio: **0**
- Missing / not extractable from static HTML: branches, services, coverage, official_delivery_times, official_pricing, weight_limits, size_limits, insurance, tracking, working_hours, customer_support

## Coverage percentage summary

| Company | Province coverage % | City coverage % (vs target 100) | Branch coverage % (vs target 200) | Review confidence |
|---|---:|---:|---:|---:|
| Tipax | 93.55 | 42.0 | 100.0 | 1.0 |
| Chapar | 25.81 | 7.0 | 9.5 | 1.0 |
| Post | 6.45 | 2.0 | 4.0 | 1.0 |
| Mahex | 22.58 | 4.0 | 8.5 | 1.0 |
| AloPeyk | 12.9 | 3.0 | 4.0 | 0.86 |
| Pishro | 0.0 | 0.0 | 0.0 | 0.05 |

## Confidence improvement opportunities

1. **Pishro:** zero/low Maps evidence and `pishro.net` currently returns maintenance page — need live site or alternate official domain + Maps discovery under additional query variants.
2. **Post:** `post.ir` connection resets from this environment — retry via alternate hosts/CDN or mirrored official pages; expand Maps queries across all 31 provinces.
3. **Fixed public tariffs / weight / size limits:** official sites mostly expose calculators, not static tables — capture calculator API responses only if officially documented, or store “calculator_only” with low confidence.
4. **Raise every company to n≥100 reviews** for strong statistical confidence on satisfaction/complaint metrics.
5. **Normalize province/city fields** during ingest (already applied in this report) to avoid inflated province counts.
6. **Branch locator JS apps** (Tipax/Chapar/Mahex agencies pages) need browser rendering to extract full official branch lists.
7. **Do not change `postal_score_v1` until** review n≥30 for all companies and official completeness ≥0.5 for reachable sites.

## postal_score_v1 status

**Unchanged.** This report and metric confidence layer are dataset quality instruments only.
