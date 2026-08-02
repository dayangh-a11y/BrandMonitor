# Remaining Work Before Public Launch

The MVP is **demonstrable** end-to-end (analyze → insights → score_v1 → API/demo).  
Private beta hardening (API token, beta-cycle cron, browser session/proxy, durable metrics, FA live QA tooling) is documented in `docs/PRIVATE_BETA.md`.

## Must-have before public beta

1. **Reliable live review yield** — use residential proxy + `BROWSER_STORAGE_STATE`; Google limited-view may still block.
2. **Hosted deploy** — TLS, reverse proxy, backups cron, log shipping, uptime check on `/health`.
3. **Live OpenAI QA in ops** — schedule `scripts/run_live_ai_qa.sh` with a real key and track regressions.
4. **Legal / ToS** — scraping and public display of third-party reviews need explicit policy review.

## Should-have shortly after private beta

1. Durable job runner (not only in-process scheduler / cron scripts)
2. Postgres (or managed SQLite HA) for concurrent writers
3. Admin actions: trigger crawl / MVP pipeline from dashboard
4. Alerting on failed crawls / empty review yield / AI backlog

## Done for MVP / private beta tooling (no longer blockers for a closed beta)

- score_v1 engine from `review_analyses`
- Automatic insights generation
- `scripts/run_mvp_pipeline.py` integration path
- OpenAI adapter behind unchanged `ModelAdapter`
- Public API `API_TOKEN` gate
- `scripts/run_beta_cycle.py` crawl→pipeline path
- Durable `ops_metric_samples` + admin exposure
- Browser proxy / storage_state hooks

## Explicit non-goals until later

- Full product marketing site / redesign of demo UI
- Multi-tenant SaaS billing
- Changing frozen contracts without a version bump
