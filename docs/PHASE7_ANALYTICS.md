# Phase 7 — Executive Analytics Dashboard

BrandMonitor analytics layer on top of existing reviews, analyses, scores, and insights.  
**Does not redesign** scoring, AI adapters, or public company/branch REST contracts.

## 1. Architecture

```text
reviews + review_analyses + branches + *_scores + *_insights
                    │
                    ▼
        analytics/service.py  (filter → aggregate → snapshot)
                    │
        analytics_snapshots (SQLite precompute / TTL cache)
                    │
        ┌───────────┴────────────┐
        ▼                        ▼
 /analytics/* JSON API     /analytics/ui/* HTML + Chart.js
        │
   export: JSON / CSV / Excel / PDF / SVG charts
```

- Aggregations live in `analytics/compute.py` (pure functions).
- Filters in `analytics/filters.py` (date, geo, branch, rating, sentiment, categories, grain).
- Snapshots avoid rescanning all reviews on every request (`analytics_snapshots`, TTL 300s).
- UI is a separate interactive dashboard (not a rewrite of `/demo`).

## 2. Endpoints

### JSON API (`API_TOKEN` required)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/analytics/companies/{id}` | Full company executive dashboard |
| GET | `/analytics/branches/{id}` | Full branch dashboard |
| GET | `/analytics/compare?mode=company\|branch\|province\|city\|period&ids=&names=` | Comparisons |
| POST | `/analytics/refresh` | Recompute all snapshots |
| GET | `/analytics/companies/{id}/export?format=json\|csv\|excel\|pdf\|png` | Export |
| GET | `/analytics/branches/{id}/export?format=...` | Export |

Shared query filters: `date_from`, `date_to`, `province`, `city`, `branch_id`, `rating_min`, `rating_max`, `sentiment`, `complaint_category`, `positive_category`, `min_review_count`, `trend_grain=daily|weekly|monthly`, `refresh=true`.

### HTML UI

| Path | Purpose |
|------|---------|
| `/analytics/ui?api_token=...` | Company picker |
| `/analytics/ui/companies/{id}` | Interactive company dashboard |
| `/analytics/ui/branches/{id}` | Interactive branch dashboard |
| `/analytics/ui/compare?...` | Comparison view |

## 3. Database additions

Table `analytics_snapshots` (`migrations/006_analytics_snapshots.sql`):

| Column | Meaning |
|--------|---------|
| `entity_type` | `company` / `branch` |
| `entity_id` | target id |
| `snapshot_kind` | e.g. `company_dashboard` |
| `filter_hash` | hash of active filters |
| `payload_json` | full dashboard JSON |
| `computed_at` | ISO timestamp |

Also reuses append-only `company_scores` / `branch_scores` for score trends.

## 4. Performance report

Measured on seeded demo DB (`data/analytics_demo.db`: 2 companies, 7 branches, 103 reviews):

| Scenario | Result |
|----------|--------|
| Tipax company dashboard force refresh (62 reviews) | **~4.6 ms** end-to-end (`build_ms` ≈ 3.2) |
| Same filters second request | **cache hit ~0.24 ms** |
| Export CSV/Excel/PDF/SVG | from snapshot payload (no second scan) |
| Full `refresh_all` during seed | 2 companies + 7 branch snapshots |

Artifact: `/opt/cursor/artifacts/phase7_performance.json`  
Design: serve `analytics_snapshots` while `computed_at` age ≤ TTL (300s); `refresh=true` or `POST /analytics/refresh` forces recompute.

## 5. Example screenshots

```bash
PYTHONPATH=. python3 scripts/seed_analytics_demo.py --db data/analytics_demo.db
BRANDMONITOR_ENV=development API_TOKEN=dev-api-token ADMIN_TOKEN=dev-admin-token \
  DB_PATH=data/analytics_demo.db PYTHONPATH=. \
  uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open:

- http://127.0.0.1:8000/analytics/ui?api_token=dev-api-token
- Company Tipax / Branch Tipax HQ / Compare Tipax vs Chapar

Captured under `/opt/cursor/artifacts/phase7_analytics/`:

- `analytics_home.webp`
- `analytics_company_top.webp` / `analytics_company_charts.webp` / `analytics_company_filtered.webp`
- `analytics_branch_top.webp` / `analytics_branch_charts.webp`
- `analytics_compare.webp`

Demo video: `/opt/cursor/artifacts/brandmonitor-phase7-analytics-demo.mp4`

## 6. Remaining improvements

1. Server-side true PNG rasterization (currently SVG chart export).
2. Richer PDF layout (multi-page branded reports).
3. Materialized daily rollup table for multi-million review scale.
4. Websocket/live refresh of snapshots after crawl/MVP pipeline.
5. Authz per tenant (today: shared `API_TOKEN`).
6. Map heatmap GIS layer for provinces/cities.

## Company dashboard coverage

Overall score, reviews, branches, avg rating, sentiment, review/rating/score trends, complaint/positive rankings, province/city distributions, top/lowest branches, ranking table, AI summary, improvements, strengths, CSI, confidence — plus Chart.js visuals and filters/export/compare.

## Branch dashboard coverage

Branch/Google/AI ratings, review count, rating/score trends, monthly volume, complaint/positive breakdowns, timeline, staff mentions, delivery/service/damage/tracking/pricing/professionalism analyses, AI summary, suggestions, historical score changes.
