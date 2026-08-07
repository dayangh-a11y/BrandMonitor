# Sprint 3 — Massive Data Collection (Production Crawler)

No ML. No prediction. No feature engineering.

Goal: reliably crawl the entire historical race archive.

## Flow

```
race_list (racecards index)
   → discover all week IDs (hrefs + leagues archive payload)
week jobs
   → expand `_weekInfo.races[].round` → per-round race URLs
race jobs
   → RaceCollector + Raw persist
   → source_hash skip when unchanged
```

## Commands

```bash
python main.py init-db
python main.py crawler discover
python main.py crawler run --workers 4
python main.py crawler refresh          # re-check successful races for updates
python main.py crawler resume           # retry failed pages
python main.py crawler progress
python main.py crawler dashboard
python main.py crawler daily-report
```

## Settings (`.env`)

| Variable | Default | Meaning |
|----------|---------|---------|
| `CRAWL_SEED_URL` | `https://asbdavani.app/racecards` | Discovery root |
| `CRAWL_DELAY_SECONDS` | `1.5` | Delay between page fetches per worker |
| `CRAWL_WORKERS` | `2` | Parallel workers |
| `CRAWL_MAX_ATTEMPTS` | `3` | Retries per job |
| `CRAWL_COLLECT_HISTORIES` | `false` | Also crawl horse histories (slower) |
| `CRAWL_STALE_RUNNING_SECONDS` | `3600` | Re-queue crashed running jobs |

## Guarantees

1. Crawl all discoverable race pages (weeks → rounds)
2. Auto-discover new races on each `discover` / `run` seed
3. Resume after interruption (`resume` + stale running recovery)
4. Skip already queued/successful URLs (dedupe key)
5. Detect updates via Raw `source_hash` (`refresh` + `skipped_unchanged`)
6. Multi-worker safe claim (Postgres `SKIP LOCKED`, SQLite optimistic update)
7. Configurable crawl delay
8. Every failure logged (`last_error` + Loguru)
9. Retry failed pages until `max_attempts`
10. Crawl statistics in `crawl_runs` + daily reports

## Dashboard metrics

Total races / horses / jockeys / trainers / owners / race videos, crawl speed, failed pages, success rate, estimated remaining work.
