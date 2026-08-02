# Remaining Work Before Public Launch

The MVP is **demonstrable** end-to-end (analyze → insights → score_v1 → API/demo).

## Must-have before public beta

1. **Reliable live review yield** — Google Maps limited-view / anti-bot often returns branches without reviews.
2. **Auth for public API** — API keys or session auth before any internet exposure.
3. **Hosted deploy** — TLS, reverse proxy, backups cron, log shipping, uptime check on `/health`.
4. **Live OpenAI QA** — run `scripts/evaluate_ai.py --live` on Persian golden set periodically.
5. **Observability beyond in-process metrics** — persist metrics so restarts do not wipe history.
6. **Legal / ToS** — scraping and public display of third-party reviews need explicit policy review.

## Should-have shortly after private beta

1. Durable job runner (not only in-process scheduler)
2. Postgres (or managed SQLite HA) for concurrent writers
3. Admin actions: trigger crawl / MVP pipeline from dashboard
4. Alerting on failed crawls / empty review yield / AI backlog

## Done for MVP demo (no longer blockers)

- score_v1 engine from `review_analyses`
- Automatic insights generation
- `scripts/run_mvp_pipeline.py` integration path
- OpenAI adapter behind unchanged `ModelAdapter`

## Explicit non-goals until later

- Full product marketing site / redesign of demo UI
- Multi-tenant SaaS billing
- Changing frozen contracts without a version bump
