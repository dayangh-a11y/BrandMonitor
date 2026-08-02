# Phase 5 Reports — Test, Performance, Stress

Generated as part of Phase 5 (Production Readiness). Re-run with:

```bash
PYTHONPATH=. python3 -m pytest tests/test_phase5_ops.py tests/test_phase5_stress.py -q -s
PYTHONPATH=. python3 -m pytest tests/ -q
```

## 1. Test report

| Suite | Scope | Result |
|-------|--------|--------|
| `tests/test_phase5_ops.py` | Config profiles, structured loggers, metrics, interrupt+retry, duplicate imports, backup/export, admin monitoring/health (token gate), scheduler manual/schedule | Expected PASS |
| `tests/test_phase5_stress.py` | 50,000 review bulk ingest; 1,000-branch crawl orchestration | Expected PASS |
| Existing suites | Parser, Phase2 schema, AI E2E, API, crawl pipeline/stress 5k | Must remain PASS |

### Scenarios covered

1. **Interrupted / failed crawl** — branch hard-fails → `retry-failed` re-queues → resume succeeds.
2. **Duplicate imports** — batch upsert + incremental filter → zero new inserts on replay.
3. **Admin auth** — `/admin/*` without token → 401; with token → 200; public `/health` unchanged.
4. **Backup tools** — SQLite copy, CSV trio, JSON tree export.
5. **Environments** — `development` / `staging` / `production` (prod requires `ADMIN_TOKEN`).

## 2. Performance report

Targets measured in-process (no Google network):

| Workload | Metric | Target |
|----------|--------|--------|
| 50k review batch upsert | wall time | < 180s |
| 50k review batch upsert | throughput | recorded in `METRICS` `crawl_speed_reviews_per_sec` |
| 1k branches × 2 reviews | wall time | < 300s |
| 1k branches | success | 1000 succeeded tasks, 2000 reviews |

Notes:

- Per-row `upsert_review` commits are fine for live Maps volumes; `upsert_reviews_batch` is the high-volume path.
- Admin dashboard aggregates are O(recent runs) with capped limits.
- API workers must stay at 1 while SQLite is the system of record.

## 3. Stress test report

| Test | Volume | Assertions |
|------|--------|------------|
| `test_stress_50000_fake_reviews` | 50,000 reviews | count==50000; duplicate upsert stable; metrics recorded |
| `test_stress_1000_branches` | 1,000 branches / 2,000 reviews | all branches succeeded; ops dashboard avg reviews/branch == 2 |

Prior Phase 4 baseline: 20×250 = 5,000 simulated reviews via full crawler path (still in `tests/test_crawl_stress.py`).

## 4. Logging / metrics checklist

| Component logger | Used by |
|-----------------|---------|
| `crawler` | `ProductionCrawler` |
| `ai_worker` | `AnalysisWorker` |
| `scoring` | reserved (engine not in Phase 5 scope) |
| `api` | FastAPI admin + lifecycle |
| `scheduler` | `CrawlScheduler` / CLI |
| `ops` | backup/export |

Metrics: crawl speed, duplicate rate, failed branch rate, AI latency, AI throughput proxy.
