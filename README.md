# BrandMonitor

AI-powered logistics review intelligence platform (Iran MVP).

## Current stage (Phase 1)

Google Maps collector that:

1. Searches a courier brand (e.g. تیپاکس)
2. Collects branch cards
3. Opens each branch and extracts reviews
4. Persists companies / branches / reviews into SQLite
5. Also exports CSV under `output/`

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

cp .env.example .env
python main.py
```

## Smoke test

```bash
python scripts/smoke_test.py
echo $?
# 0 = branches + reviews OK
# 2 = branches OK, reviews blocked/empty
# 1 = failed
```

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `SEARCH_QUERY` | تیپاکس | Brand to search |
| `MAX_BRANCHES` | 3 | Branch limit per run |
| `MAX_REVIEWS_PER_BRANCH` | 20 | Review limit per branch |
| `DB_PATH` | `data/brandmonitor.db` | SQLite path |
| `HEADLESS` | `true` | Browser mode |

## Architecture direction

```text
Collectors (Google Maps, ...)
        ↓
Platform Core (Postgres/SQLite + AI jobs + scoring)
        ↓
Public pages + Admin dashboard
```

Phase 1 focuses on reliable ingestion. AI scoring and product UI come next.
