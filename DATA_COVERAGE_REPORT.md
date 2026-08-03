# DATA_COVERAGE_REPORT

**Goal:** improve dataset coverage and confidence first; `postal_score_v1` unchanged.

**Generated from:** Maps warehouses + `data/coverage_expand/*` + official website harvest.

## Executive totals

| Metric | Value |
|--------|------:|
| Companies | 6 |
| Branches (deduped) | 477 |
| Reviews | 2504 |
| Avg overall dataset confidence | 0.487 |

Targets used for confidence: reviews≥100 full, branches≥200, cities≥100, provinces≥31.
Statistical minimum for review metrics: **n≥30** (strong: n≥100).

## Per-company coverage

| Company | Branches | Cities | Provinces | Reviews | Prov coverage % | Official completeness | Overall dataset confidence | Stats-ready (reviews≥30) |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|
| Tipax | 369 | 42 | 29 | 1804 | 93.55 | 0.636 | 0.878 | yes |
| Chapar | 28 | 8 | 9 | 217 | 29.03 | 0.727 | 0.546 | yes |
| Post | 32 | 3 | 4 | 248 | 12.9 | 0 | 0.412 | yes |
| Mahex | 30 | 5 | 8 | 102 | 25.81 | 0.455 | 0.499 | yes |
| AloPeyk | 9 | 3 | 4 | 93 | 12.9 | 0.364 | 0.414 | yes |
| Pishro | 9 | 4 | 4 | 40 | 12.9 | 0 | 0.175 | yes |

## Number of branches / cities / provinces / reviews

### Tipax

- Branches covered: **369**
- Cities: **42**
- Provinces: **29** (93.55% of 31)
- Reviews: **1804**
- Coverage vs branch target (200): **100.0%**
- Sources: tipax_iran.db

Metric confidence:

| Metric | Value | Confidence |
|--------|------:|-----------:|
| reviews | 1804 | 1.0 |
| branches | 369 | 1.0 |
| cities | 42 | 0.42 |
| provinces | 29 | 0.935 |
| official_profile | 0.636 | 0.636 |
| overall | — | 0.878 |

### Chapar

- Branches covered: **28**
- Cities: **8**
- Provinces: **9** (29.03% of 31)
- Reviews: **217**
- Coverage vs branch target (200): **14.0%**
- Sources: analytics_demo.db, chapar_coverage.db, phase11_multisource.db

Metric confidence:

| Metric | Value | Confidence |
|--------|------:|-----------:|
| reviews | 217 | 1.0 |
| branches | 28 | 0.14 |
| cities | 8 | 0.08 |
| provinces | 9 | 0.29 |
| official_profile | 0.727 | 0.727 |
| overall | — | 0.546 |

### Post

- Branches covered: **32**
- Cities: **3**
- Provinces: **4** (12.9% of 31)
- Reviews: **248**
- Coverage vs branch target (200): **16.0%**
- Sources: phase11_multisource.db, post_coverage.db

Metric confidence:

| Metric | Value | Confidence |
|--------|------:|-----------:|
| reviews | 248 | 1.0 |
| branches | 32 | 0.16 |
| cities | 3 | 0.03 |
| provinces | 4 | 0.129 |
| official_profile | 0.0 | 0.0 |
| overall | — | 0.412 |

### Mahex

- Branches covered: **30**
- Cities: **5**
- Provinces: **8** (25.81% of 31)
- Reviews: **102**
- Coverage vs branch target (200): **15.0%**
- Sources: mahex_coverage.db, phase11_multisource.db

Metric confidence:

| Metric | Value | Confidence |
|--------|------:|-----------:|
| reviews | 102 | 1.0 |
| branches | 30 | 0.15 |
| cities | 5 | 0.05 |
| provinces | 8 | 0.258 |
| official_profile | 0.455 | 0.455 |
| overall | — | 0.499 |

### AloPeyk

- Branches covered: **9**
- Cities: **3**
- Provinces: **4** (12.9% of 31)
- Reviews: **93**
- Coverage vs branch target (200): **4.5%**
- Sources: alopeyk_coverage.db, phase11_multisource.db

Metric confidence:

| Metric | Value | Confidence |
|--------|------:|-----------:|
| reviews | 93 | 0.93 |
| branches | 9 | 0.045 |
| cities | 3 | 0.03 |
| provinces | 4 | 0.129 |
| official_profile | 0.364 | 0.364 |
| overall | — | 0.414 |

### Pishro

- Branches covered: **9**
- Cities: **4**
- Provinces: **4** (12.9% of 31)
- Reviews: **40**
- Coverage vs branch target (200): **4.5%**
- Sources: pishro_coverage.db

Metric confidence:

| Metric | Value | Confidence |
|--------|------:|-----------:|
| reviews | 40 | 0.4 |
| branches | 9 | 0.045 |
| cities | 4 | 0.04 |
| provinces | 4 | 0.129 |
| official_profile | 0.0 | 0.0 |
| overall | — | 0.175 |

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
| Chapar | 29.03 | 8.0 | 14.0 | 1.0 |
| Post | 12.9 | 3.0 | 16.0 | 1.0 |
| Mahex | 25.81 | 5.0 | 15.0 | 1.0 |
| AloPeyk | 12.9 | 3.0 | 4.5 | 0.93 |
| Pishro | 12.9 | 4.0 | 4.5 | 0.4 |

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

## Before → after this coverage pass

Baseline = pre-expansion warehouses (`tipax_iran` + `phase11` + demo). After = baseline ∪ `data/coverage_expand/*` + official website harvest.

| Company | Branches before→after | Reviews before→after | Provinces before→after | Dataset confidence before→after | Stats-ready |
|---|---|---|---|---|---|
| Tipax | 369→**369** | 1804→**1804** | 29→**29** | 0.878→**0.878** | yes |
| Chapar | 19→**28** | 122→**217** | 8→**9** | 0.528→**0.546** | yes |
| Post | 8→**32** | 55→**248** | 2→**4** | 0.372→**0.412** | yes |
| Mahex | 17→**30** | 60→**102** | 7→**8** | 0.477→**0.499** | yes |
| AloPeyk | 8→**9** | 43→**93** | 4→**4** | 0.388→**0.414** | yes |
| Pishro | 0→**9** | 0→**40** | 0→**4** | 0.042→**0.175** | yes |

Note: Tipax counts use `tipax_iran.db` only (no expansion this pass). Earlier 1866 figures double-counted overlapping DBs and were corrected.

### New Maps collection this pass

| Brand | Branches stored | Reviews new | Discovery kept/found |
|---|---:|---:|---|
| Chapar | 25 | 95 | 169/175 |
| Mahex | 25 | 42 | 85/92 |
| AloPeyk | 6 | 50 | 6/17 |
| Post | 25 | 193 | 136/142 |
| Pishro | 9 | 40 | 9/169 |

### Official website harvest completeness

| Company | Reachable | Completeness | Missing topics |
|---|---|---:|---|
| tipax | True | 0.636 | coverage, official_pricing, weight_limits, size_limits |
| chapar | True | 0.727 | coverage, weight_limits, size_limits |
| mahex | True | 0.455 | coverage, official_delivery_times, official_pricing, weight_limits, size_limits, working_hours |
| alopeyk | True | 0.364 | branches, coverage, official_delivery_times, official_pricing, weight_limits, size_limits, working_hours |
| pishro | True | 0.0 | branches, services, coverage, official_delivery_times, official_pricing, weight_limits, size_limits, insurance, tracking, working_hours, customer_support |
| post | False | 0.0 | branches, services, coverage, official_delivery_times, official_pricing, weight_limits, size_limits, insurance, tracking, working_hours, customer_support |

### postal_score_v1

**Algorithm/weights unchanged.** Point scores may move when underlying review/official inputs change; that is data refresh, not a scoring-method change.
