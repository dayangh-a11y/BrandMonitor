# Phase 11 — Geographic Analytics Dashboard

## Goal

Interactive **visualization-only** Tipax analytics over the existing SQLite database.

No crawler changes, no AI pipeline changes, no database schema changes, no frontend framework rewrite.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/analytics/companies/{id}/geo` | Geo JSON payload (pins, heatmaps, KPIs, leaderboard) |
| GET | `/analytics/companies/{id}/geo/export` | Export `json\|csv\|excel\|pdf\|png` |
| GET | `/analytics/ui/geo/{id}` | Plotly interactive dashboard |
| GET | `/analytics/ui/geo/iran.geojson` | Simplified Iran province polygons |

Auth: same `API_TOKEN` / `X-API-Token` as Phase 7 analytics.

## Dashboard sections

1. **Iran map** — choropleth provinces by average score + branch markers (color by score, size by reviews). Click marker → name, province, city, reviews, score, Google rating, AI summary, top complaints/positives.
2. **Top 10 best / worst** — horizontal ranked bars.
3. **Province heatmap** — average branch score.
4. **Review / score histograms**
5. **Sortable searchable leaderboard** — Rank, Branch, Province, City, Reviews, Google Rating, AI Score, CSI, Confidence.
6. **KPIs** — totals, avg/high/low score, avg Google rating, coverage %.
7. **Export** — CSV / Excel / PDF / PNG (server exports + client PNG/PDF of map/page).

## Demo

```bash
PYTHONPATH=. python3 scripts/seed_analytics_demo.py --db data/analytics_demo.db
PYTHONPATH=. uvicorn api.main:app --host 127.0.0.1 --port 8000
# open /analytics/ui/geo/1?api_token=...
```

## Notes

- Coverage % = provinces with ≥1 branch / 31.
- Branches without coordinates appear in leaderboard/charts but not as map pins.
- Province names are normalized (FA/EN aliases) to GeoJSON feature ids.
