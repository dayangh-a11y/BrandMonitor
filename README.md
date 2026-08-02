# BrandMonitor

AI-powered logistics review intelligence platform (Iran MVP).

## Current stage (Phase 5 — Production Readiness)

Working MVP spine:

1. Google Maps collection + production crawl (incremental, resume, dedupe)
2. AI foundation (`FakeAdapter` pipeline + jobs)
3. REST read API + demo vertical slice
4. **Ops:** admin monitoring/health, structured logs, metrics, env config, backup/export

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

cp .env.example .env
export BRANDMONITOR_ENV=development
export ADMIN_TOKEN=dev-admin-token

# API + demo + admin
PYTHONPATH=. uvicorn api.main:app --reload --port 8000
# Demo:    http://127.0.0.1:8000/demo
# Admin:   http://127.0.0.1:8000/admin/monitoring?token=dev-admin-token
# Health:  http://127.0.0.1:8000/admin/health?token=dev-admin-token
```

## Environments

| `BRANDMONITOR_ENV` | DB default | Notes |
|---|---|---|
| `development` | `data/brandmonitor.db` | debug logs, default admin token |
| `staging` | `data/staging_brandmonitor.db` | JSON logs |
| `production` | `data/prod_brandmonitor.db` | **requires** `ADMIN_TOKEN` |

See `docs/PRODUCTION.md`.

## Ops commands

```bash
# Production crawl (incremental)
PYTHONPATH=. python3 scripts/run_production_crawl.py --company تیپاکس --mode incremental --max-branches 3

# Scheduler: manual / schedule / retry-failed
PYTHONPATH=. python3 scripts/run_scheduler.py manual --company تیپاکس
PYTHONPATH=. python3 scripts/run_scheduler.py retry-failed --run-id 1

# Backup / export
PYTHONPATH=. python3 scripts/backup_export.py --format all
```

## Tests

```bash
PYTHONPATH=. python3 -m pytest tests/ -q
# Phase 5 stress (50k reviews + 1k branches) is included
```

## Documentation

| Doc | Content |
|---|---|
| `docs/PRODUCTION.md` | Deployment guide |
| `docs/PHASE5_REPORTS.md` | Test / performance / stress reports |
| `docs/REMAINING_BEFORE_LAUNCH.md` | Launch checklist |

## Architecture

```text
Collectors (Google Maps) → SQLite
        ↓
AI jobs (FakeAdapter today) → scores (seed / future engine)
        ↓
Public read API + demo UI
        ↓
Admin monitoring / health (token-gated)
```

Frozen for Phase 5+: scoring engine, product UI, public API contracts, AI architecture.
