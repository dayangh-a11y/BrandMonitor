# Phase 6 — Production Data Collection Engine

## Architecture

```text
config/companies.yaml
        │
        ▼
collectors/company_config.py ──► collectors/sources/registry.py
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
             google_maps          (future: snapp)     (future: balad)
                    │
                    ▼
         ProductionCrawler (resume / incremental / batch)
                    │
                    ▼
              SQLite (branches metadata + reviews + crawl_*)
```

Sources implement `BranchReviewSource` (`discover_branches`, `collect_reviews`, `close`).  
Scoring / AI / API are unchanged consumers of the same `reviews` table.

## Database changes

Applied via `Database._ensure_phase6_collection_columns()` (+ `migrations/004_production_collection.sql` note):

**branches:** `phone`, `latitude`, `longitude`, `city`, `province`, `metadata_json`, `last_success_at`  
**reviews:** `owner_response`, `owner_response_at`, `is_deleted`, `content_hash`, `last_seen_at`

## Commands

```bash
export PYTHONPATH=.
export DB_PATH=data/brandmonitor.db

# Manual one company (query from config or free text)
python3 scripts/run_scheduler.py manual --company تیپاکس --mode incremental --max-branches 5

# One branch
python3 scripts/run_scheduler.py manual --company تیپاکس --branch-name "Tipax HQ"

# All enabled companies from config/companies.yaml
python3 scripts/run_scheduler.py all-companies --mode incremental --max-branches 3

# Schedule from config (1 tick for smoke)
python3 scripts/run_scheduler.py schedule --from-config --ticks 1

# Retry failed tasks
python3 scripts/run_scheduler.py retry-failed --run-id 12

# Report
python3 scripts/generate_crawl_report.py --run-id 12
```

## Manual testing guide

1. Edit `config/companies.yaml` — enable/disable companies; no code changes.
2. Run `manual` for one company with `--max-branches 2`.
3. Re-run same command — expect `reviews_new=0` when nothing changed.
4. Interrupt a run (Ctrl+C) then resume via `retry-failed` or re-run (resumable run detection).
5. Check admin: `/admin/monitoring?token=...` for job counts.
6. Inspect DB branch columns: phone/city/coords when Maps exposes them.

## Stress test results (this environment)

| Test | Result |
|------|--------|
| `test_batch_stress_and_schema` 5k batch upsert | PASS |
| `test_production_collection_*` (diff/resume/deleted/one-branch) | PASS |
| Existing `test_crawl_stress` 5k crawler path | PASS |
| Phase 5 50k batch / 1k branches | Still available |

Re-run:

```bash
PYTHONPATH=. python3 -m pytest tests/test_production_collection.py tests/test_crawl_pipeline.py tests/test_crawl_stress.py -q
```

## Crawl report example

```json
{
  "run_id": 1,
  "company_name": "تیپاکس",
  "mode": "incremental",
  "status": "succeeded",
  "branches_discovered": 2,
  "branches_succeeded": 2,
  "reviews_found": 3,
  "reviews_new": 3,
  "reviews_updated": 0,
  "reviews_deleted": 0,
  "retries": 0
}
```

`reviews_updated` = **edited** content only (content_hash change). Identical rescrape → updated=0.

## Performance metrics

- Batch `upsert_reviews_batch` used on the production crawl path (single commit per branch).
- Avoids per-review commits for high volume.
- In-process metrics: crawl speed, duplicate rate, failed branch rate (`core/metrics.py`).

## Known limitations

1. Google Maps limited-view / anti-bot can block review panes.
2. Scroll is capped by `max_reviews_per_branch` / scroll rounds — “all reviews” depends on Google UI.
3. City/province inference is heuristic from address text when Maps doesn’t expose structured fields.
4. Owner-response selectors are best-effort and locale-sensitive.
5. SQLite + single worker remains the concurrency model.
6. Metrics are in-process unless exported.

## Remaining work before public beta

1. Residential / authenticated Maps sessions for reliable live yield.
2. Durable crawl metrics store + alerting.
3. Additional sources via `collectors/sources/registry.py` (Snapp, Balad, sites).
4. Legal review of scraping/storage.
5. Optional Postgres if multi-writer scale is required.
