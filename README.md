# BrandMonitor

AI-powered **Postal Intelligence Platform** for Iranian logistics companies.

## Platform status

BrandMonitor compares postal companies using:

- explainable **0–100 postal scores** (weighted dimensions, not ratings alone)
- a curated **official company dataset** (services, pricing, coverage, COD, …)
- **branch intelligence**, geo rankings, comparison tables, and dashboards

Review collection remains available; Phase 2 focuses on intelligence & comparison.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export BRANDMONITOR_ENV=development
export ADMIN_TOKEN=dev-admin-token
export API_TOKEN=dev-api-token
export AI_PROVIDER=fake   # or openai + OPENAI_API_KEY
export DB_PATH=data/brandmonitor.db
export PYTHONPATH=.

# Build Postal Intelligence Platform (official data + existing review DBs)
python3 scripts/build_postal_intelligence.py

# Legacy MVP seed (reviews → AI → score_v1)
python3 scripts/seed_demo_data.py --db "$DB_PATH"

# Serve
uvicorn api.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Open:

- **Postal Intelligence demo:** http://127.0.0.1:8000/intel
- Pricing calculator feasibility: `docs/postal_intelligence/PRICING_CALCULATOR_FEASIBILITY.md`
- Pricing & ETA engine: `docs/postal_intelligence/PRICING_ETA_ENGINE.md` (`/postal/pricing/*`)
- Iran Post module: `docs/postal_intelligence/IRAN_POST_MODULE.md` (`/postal/iran-post/*`)
- Postal dashboards: `output/postal_intelligence/dashboards/index.html` (or `docs/postal_intelligence/dashboards/`)
- Postal API: `/postal/*` (requires `X-API-Token`)
- Legacy review demo: http://127.0.0.1:8000/demo
- API docs: http://127.0.0.1:8000/docs
- Executive analytics: `/analytics/ui`
- Admin: http://127.0.0.1:8000/admin/monitoring?token=dev-admin-token

## Modules

| Area | Status |
|------|--------|
| Postal Intelligence scoring (`postal_score_v1`) | Ready (`postal/`, configurable weights) |
| Official company dataset | Ready (`config/official_companies.yaml`) |
| Branch intelligence + geo rankings | Ready |
| Company comparison tables | Ready |
| Postal dashboards + map | Ready (`output/postal_intelligence/dashboards`) |
| Google Maps collector + production crawl | Ready |
| AI analysis (`FakeAdapter` / `OpenAIAdapter`) | Ready |
| Legacy score_v1 engine | Ready (`scoring/`) |
| REST read API | Ready (`API_TOKEN` gate) |
| Executive analytics dashboards | Ready (`/analytics/ui`, Phase 7) |

## Key commands

```bash
python3 scripts/build_postal_intelligence.py
python3 scripts/run_production_crawl.py --company تیپاکس --mode incremental --max-branches 3
python3 scripts/run_scheduler.py manual --company تیپاکس --mode incremental
python3 scripts/run_ai_analysis.py --limit 100
python3 scripts/run_scoring.py --insights
python3 scripts/run_mvp_pipeline.py
python3 -m pytest tests/ -q
```

Company registry: `config/companies.yaml`. Scoring weights: `config/scoring_weights.yaml`.

## Docs

- `docs/POSTAL_INTELLIGENCE.md` — platform architecture
- `docs/SCORING_METHODOLOGY.md` — every score formula (no black box)
- `docs/PRODUCTION.md` — deploy / env
- `docs/PRIVATE_BETA.md` — API auth, beta cycle
- `docs/PHASE7_ANALYTICS.md` — executive analytics
- `docs/MVP_ENGINEERING_REPORT.md` — MVP integration report

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
