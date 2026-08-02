# BrandMonitor Production Deployment Guide

## 1. Environments

Set `BRANDMONITOR_ENV` to one of:

| Profile | Purpose |
|---------|---------|
| `development` | Local iteration, human-readable logs |
| `staging` | Pre-prod validation, JSON logs |
| `production` | Live; requires `ADMIN_TOKEN` |

Loaded via `core.config.load_settings()`.

### Required / important variables

| Variable | Default (dev) | Meaning |
|----------|---------------|---------|
| `BRANDMONITOR_ENV` | `development` | Profile |
| `DB_PATH` | profile default | SQLite file |
| `ADMIN_TOKEN` | `dev-admin-token` | Admin dashboard gate (**required in production**) |
| `API_TOKEN` | `dev-api-token` | Public REST API gate (**required in production**) |
| `LOG_LEVEL` | `DEBUG`/`INFO` | Logging level |
| `LOG_JSON` | `false`/`true` | Structured JSON logs |
| `CRAWL_MAX_ATTEMPTS` | `3`/`5` | Branch task retries |
| `CRAWL_DEFAULT_MODE` | `incremental` | Scheduler default |
| `BACKUP_DIR` | `backups` | Export output root |
| `HEADLESS` | `true` | Playwright mode |
| `BROWSER_PROXY` | _(empty)_ | Playwright proxy (`http://host:port`); falls back to `HTTPS_PROXY`/`HTTP_PROXY` |
| `BROWSER_STORAGE_STATE` | _(empty)_ | Path to Playwright `storage_state` JSON (load/save session) |
| `BROWSER_LOCALE` | `en-US` | Browser locale (e.g. `fa-IR`) |

## 2. Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
mkdir -p data backups logs
```

## 3. Run API

```bash
export BRANDMONITOR_ENV=production
export ADMIN_TOKEN='replace-me'
export API_TOKEN='replace-me-api'
export DB_PATH=data/prod_brandmonitor.db
export LOG_JSON=true

PYTHONPATH=. uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 1
```

SQLite + crawl scheduler are single-process friendly; keep `workers=1` unless you move the DB to Postgres and externalize the scheduler.

### Endpoints

| Path | Audience |
|------|----------|
| `/health` | Public liveness (unchanged contract) |
| `/docs` | OpenAPI |
| `/demo` | Product demo slice |
| `/admin/monitoring?token=...` | Admin crawl dashboard |
| `/admin/health?token=...` | Admin system health |
| `/admin/metrics.json?token=...` | Metrics + health JSON |

Pass `X-Admin-Token` header or `?token=` query for admin routes.  
Pass `X-API-Token` (or `Authorization: Bearer`) for public REST routes. See `docs/PRIVATE_BETA.md`.

## 4. Crawl operations

```bash
# One-shot incremental crawl
PYTHONPATH=. python3 scripts/run_production_crawl.py \
  --company تیپاکس --mode incremental --max-branches 5

# Manual via scheduler CLI
PYTHONPATH=. python3 scripts/run_scheduler.py manual --company تیپاکس

# Retry failed branch tasks on a run
PYTHONPATH=. python3 scripts/run_scheduler.py retry-failed --run-id 12

# Report
PYTHONPATH=. python3 scripts/generate_crawl_report.py --run-id 12

# Full private-beta cycle: crawl → AI → insights → scores
PYTHONPATH=. python3 scripts/run_beta_cycle.py --max-branches 5
```

Cron example (staging/production host) — prefer beta cycle:

```cron
0 */6 * * * cd /opt/brandmonitor && . .venv/bin/activate && \
  BRANDMONITOR_ENV=production ADMIN_TOKEN=*** API_TOKEN=*** \
  PYTHONPATH=. python3 scripts/run_beta_cycle.py --max-branches 10 \
  >> logs/beta_cycle.log 2>&1
```

## 5. Backup / export

```bash
PYTHONPATH=. python3 scripts/backup_export.py --format all
# Creates backups/<timestamp>/{brandmonitor.db,csv/,brandmonitor.json}
```

Recommended: daily SQLite copy + weekly JSON export off-box.

## 6. Logging & metrics

- Components: `crawler`, `ai_worker`, `scoring`, `api`, `scheduler`, `ops`
- Enable JSON: `LOG_JSON=true`
- In-process metrics: crawl speed, duplicate rate, AI latency/throughput — exposed on `/admin/metrics.json`
- Durable samples: flushed to `ops_metric_samples` (survives restart); also listed under `durable_metric_samples`

## 7. Health checks

- Process: `GET /health` → `{ "status": "ok", "stats": ... }`
- Ops: `GET /admin/health?token=...` → DB size, queue, failed jobs, last successful crawl, AI status

## 8. Security baseline

1. Set strong `ADMIN_TOKEN` and `API_TOKEN` in production.
2. Do not expose `/admin/*` without TLS and network allowlisting.
3. Public REST API requires `API_TOKEN`; still put the host behind TLS (+ VPN if possible).
4. Keep `/demo` on a private network for beta (HTML is not API-token gated).
5. Do not commit `.env` or production DB files.

## 9. Rollback

1. Stop uvicorn / crawl cron.
2. Restore latest `backups/*/brandmonitor.db` over `DB_PATH`.
3. Restart API with the same `BRANDMONITOR_ENV`.

## 10. What not to change in prod hotfixes

- Public API response schemas
- `AnalysisDTO` / AI adapter interface
- Product demo UI
- Scoring algorithm tables without a version bump
