# BrandMonitor Postal Intelligence Demo

Investor-ready interactive demo at **`/intel`**.

## Run

```bash
# ensure warehouse exists
PYTHONPATH=. python3 scripts/build_postal_intelligence.py

# start API
PYTHONPATH=. uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open:

| Route | Purpose |
|-------|---------|
| `/intel` | Home dashboard — ranking, KPIs, confidence, charts, map |
| `/intel/companies/{slug}` | Company profile + AI executive summary |
| `/intel/branches/{id}` | Branch profile, reviews, sentiment, complaints |
| `/intel/insights` | AI Insights (evidence-bound) |
| `/intel/compare?a=&b=` | AI Compare any two companies |
| `/intel/search?q=` | Natural-language AI Search |

JSON helpers: `/intel/api/snapshot`, `/intel/api/search`, `/intel/api/compare`.

## Screenshots

<img alt="Intel dashboard" src="screenshots/demo_home.png" />
<img alt="Company profile" src="screenshots/demo_company_chapar.png" />
<img alt="AI Compare" src="screenshots/demo_compare.png" />
<img alt="AI Search" src="screenshots/demo_search.png" />
<img alt="AI Insights" src="screenshots/demo_insights.png" />
<img alt="Branch profile" src="screenshots/demo_branch.png" />

## AI rules

- Narratives are deterministic summaries of warehouse tables only.
- Every insight shows **data sources**, **confidence**, and **last update**.
- If evidence is thin (e.g. &lt;30 reviews), the UI states insufficiency explicitly.
- Confidence grades dataset coverage; it does **not** alter `postal_score_v1`.
