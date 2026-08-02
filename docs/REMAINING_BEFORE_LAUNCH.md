# Remaining Work Before Public Launch

Phase 5 makes BrandMonitor **operable**. It does **not** make it a public scoring product yet.

## Must-have before public beta

1. **Reliable live review yield** — Google Maps limited-view / anti-bot often returns branches without reviews. Need residential sessions, authenticated flows, or alternate sources.
2. **Real AI adapter** — replace `FakeAdapter` for production Persian/English quality (architecture stays; new adapter class only).
3. **Scoring engine `score_v1`** — implement deterministic scoring from `review_analyses` (schema/API already expect it). Demo seed scores are not trustworthy.
4. **Auth for public API** — API keys or session auth before any internet exposure.
5. **Hosted deploy** — TLS, reverse proxy, backups cron, log shipping, uptime check on `/health`.
6. **Observability beyond in-process metrics** — persist metrics/events (Prometheus/OpenTelemetry or DB rollups) so restarts do not wipe history.
7. **Legal / ToS** — scraping and public display of third-party reviews need explicit policy review.

## Should-have shortly after private beta

1. Durable job runner (not only in-process scheduler)
2. Postgres (or managed SQLite HA) for concurrent writers
3. Insight generation jobs (branch/company summaries)
4. Admin actions: trigger crawl, drain AI queue, from the dashboard UI
5. Alerting on failed crawls / empty review yield / AI backlog

## Explicit non-goals until later

- Full product marketing site / redesign of demo UI
- Multi-tenant SaaS billing
- Non–Google Maps collectors (after Maps yield is stable)
- Changing frozen contracts: public API shapes, `AnalysisDTO`, scoring table semantics without version bump

## Suggested Phase 6 (approval required)

**Close the intelligence loop for private beta:** OpenAI (or other) adapter + `score_v1` engine + batch analyze→score after crawl — without changing public API contracts or demo routes.

Do not start Phase 6 until explicitly approved.
