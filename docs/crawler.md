# Sprint 3 — Massive Data Collection (Production Crawler)

No ML. No prediction. No feature engineering.

Goal: crawl **100% of historical races** for the configured racecourses only.

## Racecourse scope (required)

Default allowlist (Golestan triad):

| Code | English | Persian |
|------|---------|---------|
| `gonbad-kavous` | Gonbad Kavous | گنبدکاووس |
| `aq-qala` | Aq Qala | آق قلا |
| `bandar-torkaman` | Bandar Torkaman | بندرترکمن |

All other racecourses are ignored. This is **not** a nationwide crawl.

Enable additional tracks later by:

1. Registering the course in `src/racecourses/registry.py` (aliases + canonical names)
2. Adding its code to `CRAWL_ALLOWED_RACECOURSES`

No database redesign is required — races store `track` + `racecourse_code` (both required).

## Flow

```
race_list (racecards index)
   → discover weeks, filter by allowed racecourse location
week jobs
   → resolve location from week HTML; skip out-of-scope
   → expand `_weekInfo.races[].round` → per-round race URLs
race jobs
   → RaceCollector + Raw persist (horses, results, jockeys, trainers, videos)
   → require racecourse_code + track
   → source_hash skip when unchanged
   → skipped_out_of_scope when outside allowlist
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
| `CRAWL_COLLECT_HISTORIES` | `false` | Also crawl horse profile histories |
| `CRAWL_STALE_RUNNING_SECONDS` | `3600` | Re-queue crashed running jobs |
| `CRAWL_ALLOWED_RACECOURSES` | `gonbad-kavous,aq-qala,bandar-torkaman` | Scope allowlist (`*` = nationwide, not default) |

## Guarantees

1. Collect every historical race for allowed racecourses only
2. Collect every horse / result / jockey / trainer from those races
3. Collect race videos when present in source payloads
4. Store `track` + `racecourse_code` as required fields
5. Auto-discover new in-scope races on each `discover` / `run` seed
6. Resume after interruption (`resume` + stale running recovery)
7. Skip already queued/successful URLs (dedupe key)
8. Detect updates via Raw `source_hash` (`refresh` + `skipped_unchanged`)
9. Multi-worker safe claim (Postgres `SKIP LOCKED`, SQLite optimistic update)
10. Configurable crawl delay + failure logging + retries
11. Crawl statistics in `crawl_runs` + daily reports

## Dashboard metrics

Total races / horses / jockeys / trainers / owners / race videos, crawl speed, failed pages, success rate, estimated remaining work.
