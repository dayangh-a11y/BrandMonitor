# Private Beta Hardening

Hardening slice for private beta exposure. **Does not change** `score_v1`, public response field shapes, AI adapter contracts, or demo UI layout.

## What shipped

1. **API token gate** on REST read routes (`/companies`, `/branches`, `/search`, …)
2. **Crawl → MVP cron script** (`scripts/run_beta_cycle.py`)
3. **Browser proxy + storage_state** for warmer Maps sessions
4. **Persian live AI QA** (`--language fa`, `scripts/run_live_ai_qa.sh`)
5. **Durable ops metrics** (`ops_metric_samples` table + flush after crawls)

## Auth

| Audience | Gate |
|----------|------|
| Public REST API | `API_TOKEN` via `X-API-Token`, `Authorization: Bearer`, or `?api_token=` |
| Admin pages | `ADMIN_TOKEN` (unchanged) |
| `/health` | Public (liveness) |
| `/demo` | Open HTML (uses DB server-side; put behind VPN in beta) |

```bash
export API_TOKEN=dev-api-token
curl -H "X-API-Token: $API_TOKEN" http://127.0.0.1:8000/companies
```

Production refuses to start without both `ADMIN_TOKEN` and `API_TOKEN`.

## Beta cycle (cron)

```bash
# Crawl all enabled companies, then analyze + score
PYTHONPATH=. python3 scripts/run_beta_cycle.py --max-branches 5

# Pipeline only / crawl only
PYTHONPATH=. python3 scripts/run_beta_cycle.py --skip-crawl
PYTHONPATH=. python3 scripts/run_beta_cycle.py --skip-pipeline --company تیپاکس
```

Cron example:

```cron
0 */6 * * * cd /opt/brandmonitor && . .venv/bin/activate && \
  BRANDMONITOR_ENV=production ADMIN_TOKEN=*** API_TOKEN=*** \
  PYTHONPATH=. python3 scripts/run_beta_cycle.py --max-branches 10 \
  >> logs/beta_cycle.log 2>&1
```

## Residential / session crawl

```bash
export BROWSER_PROXY=http://user:pass@residential-proxy:8000
export BROWSER_STORAGE_STATE=data/browser_storage.json
export BROWSER_LOCALE=fa-IR
PYTHONPATH=. python3 scripts/run_scheduler.py manual --company تیپاکس --max-branches 2
```

`storage_state` is loaded on start and saved after consent / on stop when the path is set.

## Live Persian AI QA

```bash
export OPENAI_API_KEY=sk-...
bash scripts/run_live_ai_qa.sh
# or:
PYTHONPATH=. python3 scripts/evaluate_ai.py --live --require-live --language fa --limit 50
```

## Durable metrics

- In-process `METRICS` still used for live gauges.
- Samples flush to `ops_metric_samples` after crawls / beta cycle.
- Admin: `/admin/metrics.json?token=...` includes `durable_metric_samples`.

## Explicitly unchanged

- Scoring engine / `score_v1`
- `AnalysisDTO` / `ModelAdapter.extract`
- Public JSON field shapes (`CompanyOut`, `ScoreOut`, …)
- Product demo HTML structure
