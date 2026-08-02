# BrandMonitor

AI-powered logistics review intelligence platform (Iran MVP).

## MVP status (demonstrable)

End-to-end path works locally:

**reviews → AI analysis → insights → score_v1 → API / demo**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export BRANDMONITOR_ENV=development
export ADMIN_TOKEN=dev-admin-token
export AI_PROVIDER=fake   # or openai + OPENAI_API_KEY
export DB_PATH=data/brandmonitor.db
export PYTHONPATH=.

# Seed demo company/branches/reviews + analyze + score
python3 scripts/seed_demo_data.py --db "$DB_PATH"

# Or refresh any DB: analyze pending + rescore everything
python3 scripts/run_mvp_pipeline.py --db "$DB_PATH"

# Serve
uvicorn api.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Open:

- Demo: http://127.0.0.1:8000/demo
- API docs: http://127.0.0.1:8000/docs
- Admin: http://127.0.0.1:8000/admin/monitoring?token=dev-admin-token

## Modules

| Area | Status |
|------|--------|
| Google Maps collector + production crawl | Ready (live review yield may be limited by Google) |
| AI analysis (`FakeAdapter` / `OpenAIAdapter`) | Ready |
| score_v1 engine | Ready (`scoring/`) |
| Insights generator | Ready (template from analyses) |
| REST read API | Ready (no auth) |
| Demo HTML | Ready |
| Admin ops pages | Ready |

## Key commands

```bash
python3 scripts/run_production_crawl.py --company تیپاکس --mode incremental --max-branches 3
python3 scripts/run_ai_analysis.py --limit 100
python3 scripts/run_scoring.py --insights
python3 scripts/run_mvp_pipeline.py
python3 scripts/backup_export.py --format all
python3 -m pytest tests/ -q
```

## Docs

- `docs/PRODUCTION.md` — deploy / env
- `docs/PHASE6_AI.md` — OpenAI adapter & prompts
- `docs/MVP_ENGINEERING_REPORT.md` — latest MVP integration report
- `docs/REMAINING_BEFORE_LAUNCH.md` — public launch checklist

## Architecture

```text
Collectors → SQLite
     ↓
AI analysis (Fake / OpenAI)
     ↓
Insights + score_v1
     ↓
Public API + Demo + Admin
```
