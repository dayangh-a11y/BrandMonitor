# MVP Engineering Report — End-to-End Integration

**Branch:** `cursor/mvp-e2e-integration-a9ca`  
**Objective:** First production-ready *demonstrable* MVP (reviews → AI → scores → API/demo).

## Completed features

1. **score_v1 scoring engine** (`scoring/engine.py`) — deterministic scores from `review_analyses` with demo-compatible components (`sentiment_score`, `kappa`, `why`, …).
2. **Insights generator** (`scoring/insights.py`) — branch/company summaries from analysis category frequencies.
3. **MVP pipeline CLI** (`scripts/run_mvp_pipeline.py`) — analyze pending reviews → insights → scores.
4. **Scoring CLI** (`scripts/run_scoring.py`) — rescore companies with optional insights refresh.
5. **Demo seed uses real engine** — no hand-authored score numbers.
6. **AI worker bugfix** — analysis `status=failed` no longer marks the job as succeeded.
7. **DB helpers** — `list_branch_analyses`, `list_pending_review_ids`.

## Files changed (this phase)

| Path | Change |
|------|--------|
| `scoring/__init__.py` | Package export |
| `scoring/engine.py` | score_v1 + ScoringEngine |
| `scoring/insights.py` | InsightsGenerator |
| `core/db.py` | Analysis listing helpers |
| `ai/worker.py` | Failed analysis → failed job |
| `scripts/run_scoring.py` | New |
| `scripts/run_mvp_pipeline.py` | New |
| `scripts/seed_demo_data.py` | Engine-backed scores/insights |
| `scripts/run_ai_analysis.py` | Use DB pending helper |
| `tests/test_scoring_engine.py` | Unit + engine E2E |
| `tests/test_mvp_e2e_api.py` | API serves engine scores |
| `README.md` | MVP quickstart |
| `docs/MVP_ENGINEERING_REPORT.md` | This report |
| `docs/REMAINING_BEFORE_LAUNCH.md` | Updated remaining items |

## Database changes

- **No new tables.** Uses existing `branch_scores`, `company_scores`, `branch_insights`, `company_insights`, `review_analyses`.
- Scores are append-only inserts (latest row wins via `ORDER BY calculated_at DESC`).

## API changes

- **None** to public contracts. Existing `/companies/{id}/score` and `/branches/{id}/score` now return real engine output when pipeline/seed has run.
- Demo and admin routes unchanged.

## AI pipeline status

| Step | Status |
|------|--------|
| Adapter (`fake` / `openai`) | Complete |
| Validation + persist | Complete |
| Cache via `input_hash` | Complete |
| Batch analyze | Complete |
| Worker job status correctness | Fixed |
| Live OpenAI | Requires `OPENAI_API_KEY` |

## Dashboard status

| Surface | Status |
|---------|--------|
| `/demo` vertical slice | Works with seeded/scored data |
| `/admin/monitoring` + `/admin/health` | Works (Phase 5) |
| AI metrics HTML file dashboard | Works (Phase 6 scripts) |

## Test results

```text
PYTHONPATH=. python3 -m pytest tests/ -q
→ 43+ passed (includes scoring + MVP API E2E)
```

Manual demo seed path verified: Tipax HQ/Vanak scores + insights populated.

## Coverage

No dedicated coverage gate in CI. Critical paths covered by unit/integration tests for parser, AI, crawl, API, scoring, and MVP API score serving. Recommend adding `pytest-cov` in a later ops phase.

## Performance impact

- score_v1 is pure Python over in-memory analysis rows — negligible vs crawl/AI.
- Seed + rescore of demo (7 reviews) completes in <1s.
- No change to crawl Playwright path.

## Remaining blockers (public launch — not MVP demo)

1. Live Google Maps review yield (anti-bot / limited view).
2. Public API authentication.
3. Durable metrics / alerting beyond in-process registries.
4. Live OpenAI golden-set validation (`evaluate_ai.py --live`).
5. Postgres / multi-worker if concurrent writers needed.
6. Legal/ToS for displaying third-party reviews.

## Recommended next phase

**Private beta hardening:** auth for API, scheduled crawl→`run_mvp_pipeline` cron, live OpenAI QA on Persian reviews, and residential crawl sessions — without changing score_v1 or public response shapes.
