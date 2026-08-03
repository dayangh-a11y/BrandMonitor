# Multi-Source Postal Intelligence Platform

Extends BrandMonitor without replacing Google Maps / Scoring / AI cores.

## Supported brands

Tipax · Iran Post · Chapar · AloPeyk · Mahex (unlimited via config + providers)

## Collector modules

| Module | Path | Status |
|--------|------|--------|
| Google Maps | `collectors/google_maps/` + `collectors/google_maps.py` | Live crawl + DB unify |
| Neshan | `collectors/neshan.py` | Manual import adapter (no fragile scrape) |
| Balad | `collectors/balad.py` | Manual import adapter |
| Cafe Bazaar | `collectors/cafebazaar.py` | Manual import adapter |
| Myket | `collectors/myket.py` | Manual import adapter |

## Unified table

`reviews_master` in `data/multisource_master.db` — one schema for every source.

## Run

```bash
# Place optional imports under data/imports/{neshan,balad,cafebazaar,myket}/
python3 scripts/run_multisource_pipeline.py
```

Outputs (also zipped as `BrandMonitor_Multisource_Platform.zip`):

- reviews_master.csv
- reviews_multisource.csv
- branches.csv / brands.csv
- complaints.csv / complaint_summary.csv / sentiment_summary.csv
- province_summary.csv / city_summary.csv / source_summary.csv
- appstore_reviews.csv
- execution_stats.json / coverage_statistics.json

## Dashboard filters

Analytics UI filters now include **Brand** and **Source** (plus existing province/city/branch/complaint/date).

## Add a source in <10 minutes

See [`ADD_NEW_SOURCE.md`](ADD_NEW_SOURCE.md).
