# Phase 5 QA Checklist — Production Readiness

**Feature under test:** BrandMonitor Phase 5 (ops, admin monitoring/health, logging, metrics, config, backup/export, scheduler retry, stress paths)  
**Branch:** `cursor/phase5-production-readiness-a9ca`  
**PR:** https://github.com/dayangh-a11y/BrandMonitor/pull/7  
**QA owner:** ________________  
**Build / commit:** ________________  
**Date:** ________________  

**Rule:** Do **not** mark Phase 5 complete until every item below is **PASS**. Any FAIL blocks release of this feature.

**Out of scope for this checklist (must still not regress):**
- Scoring engine behavior
- Product demo UI redesign
- Public API response contract changes
- AI architecture / adapter swap

---

## 0. Preconditions

| # | Check | Expected | P/F |
|---|--------|----------|-----|
| 0.1 | Clean checkout of Phase 5 branch | `git status` clean or only local QA artifacts | ☐ |
| 0.2 | Python deps installed | `pip install -r requirements.txt` succeeds | ☐ |
| 0.3 | Env for local QA | `BRANDMONITOR_ENV=development`, `ADMIN_TOKEN=dev-admin-token` | ☐ |
| 0.4 | Optional demo data | `PYTHONPATH=. python3 scripts/seed_demo_data.py` completes without error | ☐ |

```bash
cd /path/to/BrandMonitor
git checkout cursor/phase5-production-readiness-a9ca
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export BRANDMONITOR_ENV=development
export ADMIN_TOKEN=dev-admin-token
export DB_PATH=data/qa_brandmonitor.db
export PYTHONPATH=.
```

---

## 1. Commands to run

### 1.1 Automated tests (required)

| # | Command | Expected output | P/F |
|---|---------|-----------------|-----|
| 1.1.1 | `PYTHONPATH=. python3 -m pytest tests/test_phase5_ops.py -q` | `7 passed` | ☐ |
| 1.1.2 | `PYTHONPATH=. python3 -m pytest tests/test_phase5_stress.py -q -s` | `2 passed`; prints `STRESS_50K` and `STRESS_1K_BRANCHES` | ☐ |
| 1.1.3 | `PYTHONPATH=. python3 -m pytest tests/ -q` | **`32 passed`** (or current full count ≥ prior baseline; no new failures) | ☐ |

**Stress expected values (approx.):**

```text
STRESS_50K  → reviews=50000, elapsed_sec < 180 (typically ~1s)
STRESS_1K_BRANCHES → branches=1000, reviews=2000, elapsed_sec < 300 (typically ~10s)
```

### 1.2 Config / environments

| # | Command | Expected output | P/F |
|---|---------|-----------------|-----|
| 1.2.1 | `BRANDMONITOR_ENV=development PYTHONPATH=. python3 -c "from core.config import load_settings; print(load_settings().environment, load_settings().admin_token)"` | `development dev-admin-token` | ☐ |
| 1.2.2 | `BRANDMONITOR_ENV=staging PYTHONPATH=. python3 -c "from core.config import load_settings; s=load_settings(); print(s.environment, s.log_json)"` | `staging True` | ☐ |
| 1.2.3 | `BRANDMONITOR_ENV=production PYTHONPATH=. python3 -c "from core.config import load_settings; load_settings()"` | **Fails** with `ADMIN_TOKEN is required in production` | ☐ |
| 1.2.4 | `BRANDMONITOR_ENV=production ADMIN_TOKEN=qa-secret PYTHONPATH=. python3 -c "from core.config import load_settings; print(load_settings().environment)"` | `production` | ☐ |

### 1.3 Backup / export

| # | Command | Expected output | P/F |
|---|---------|-----------------|-----|
| 1.3.1 | Seed or ensure DB has ≥1 company/branch/review | DB not empty | ☐ |
| 1.3.2 | `PYTHONPATH=. python3 scripts/backup_export.py --db "$DB_PATH" --out-dir backups/qa --format all` | JSON with `sqlite`, `csv`, `json` paths | ☐ |
| 1.3.3 | Inspect export folder | Contains `brandmonitor.db`, `csv/companies.csv`, `csv/branches.csv`, `csv/reviews.csv`, `brandmonitor.json` | ☐ |

### 1.4 Scheduler CLI (smoke; live Maps optional)

| # | Command | Expected | P/F |
|---|---------|----------|-----|
| 1.4.1 | `PYTHONPATH=. python3 scripts/run_scheduler.py --help` | Shows `manual`, `schedule`, `retry-failed` | ☐ |
| 1.4.2 | *(Optional live)* `python3 scripts/run_scheduler.py manual --company تیپاکس` | JSON result + metrics; or documented Maps limited-view behavior | ☐ |
| 1.4.3 | After a run with failures: `python3 scripts/run_scheduler.py retry-failed --run-id <ID>` | `reset_tasks` ≥ 1 or clear error if run has no failures | ☐ |

### 1.5 Start API for manual / HTTP tests

```bash
export BRANDMONITOR_ENV=development
export ADMIN_TOKEN=dev-admin-token
export DB_PATH=data/qa_brandmonitor.db
PYTHONPATH=. uvicorn api.main:app --host 127.0.0.1 --port 8000 --workers 1
```

| # | Check | Expected | P/F |
|---|--------|----------|-----|
| 1.5.1 | Server starts | Log line like `api_starting env=development` | ☐ |
| 1.5.2 | No crash on boot | Process stays up | ☐ |

---

## 2. Expected outputs (quick reference)

| Action | Expected |
|--------|----------|
| Full pytest | All green; Phase 5 ops+stress included |
| Public `/health` | HTTP 200, JSON `{"status":"ok","stats":{...}}` |
| Admin without token | HTTP **401**, body `unauthorized` |
| Admin with `?token=dev-admin-token` | HTTP **200**, HTML dashboard/health |
| Backup `--format all` | Three artifact types under `backups/...` |
| Production config without token | Exception at settings load |
| Stress 50k | Exactly 50,000 reviews persisted |
| Stress 1k branches | Exactly 1,000 branches, 2,000 reviews |

---

## 3. API endpoints to test

Base: `http://127.0.0.1:8000`  
Token: `dev-admin-token` (or your `ADMIN_TOKEN`)

### 3.1 Public (must not break — regression)

| # | Method / URL | Expected | P/F |
|---|--------------|----------|-----|
| 3.1.1 | `GET /health` | 200; `status=ok`; `stats` has counts | ☐ |
| 3.1.2 | `GET /docs` | 200; Swagger UI loads | ☐ |
| 3.1.3 | `GET /companies` | 200; JSON array (may be empty) | ☐ |
| 3.1.4 | `GET /search?q=test` | 200; SearchResponse shape unchanged | ☐ |
| 3.1.5 | `GET /demo` | 200; demo HTML (product UI unchanged) | ☐ |

```bash
curl -sS http://127.0.0.1:8000/health | jq .
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/docs
curl -sS "http://127.0.0.1:8000/search?q=tipax" | jq .
```

### 3.2 Admin (Phase 5 feature)

| # | Method / URL | Expected | P/F |
|---|--------------|----------|-----|
| 3.2.1 | `GET /admin/monitoring` (no token) | **401** | ☐ |
| 3.2.2 | `GET /admin/health` (no token) | **401** | ☐ |
| 3.2.3 | `GET /admin/metrics.json` (no token) | **401** | ☐ |
| 3.2.4 | `GET /admin/dashboard.json` (no token) | **401** | ☐ |
| 3.2.5 | `GET /admin/monitoring?token=dev-admin-token` | **200** HTML; title/section “Crawl Monitoring” | ☐ |
| 3.2.6 | `GET /admin/health?token=dev-admin-token` | **200** HTML; “System Health”, DB size, queue | ☐ |
| 3.2.7 | `GET /admin/metrics.json?token=dev-admin-token` | **200** JSON with `metrics` + `health` | ☐ |
| 3.2.8 | `GET /admin/dashboard.json?token=dev-admin-token` | **200** JSON with crawl lists + pending AI fields | ☐ |
| 3.2.9 | `GET /admin/monitoring` + header `X-Admin-Token: dev-admin-token` | **200** | ☐ |
| 3.2.10 | Wrong token `?token=wrong` | **401** | ☐ |

```bash
# Auth denials
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/admin/monitoring
# expect 401

# Success via query
curl -sS -o /dev/null -w "%{http_code}\n" \
  "http://127.0.0.1:8000/admin/monitoring?token=dev-admin-token"
# expect 200

# Success via header
curl -sS -o /dev/null -w "%{http_code}\n" \
  -H "X-Admin-Token: dev-admin-token" \
  http://127.0.0.1:8000/admin/health
# expect 200

curl -sS -H "X-Admin-Token: dev-admin-token" \
  http://127.0.0.1:8000/admin/metrics.json | jq 'keys'
# expect ["health","metrics"]
```

### 3.3 Dashboard field checklist (JSON)

From `GET /admin/dashboard.json` confirm keys exist:

- [ ] `running_crawls`
- [ ] `completed_crawls`
- [ ] `failed_crawls`
- [ ] `reviews_collected_today`
- [ ] `reviews_pending_ai_analysis`
- [ ] `ai_queue_length`
- [ ] `branches_processed_recent`
- [ ] `crawl_duration`
- [ ] `average_reviews_per_branch`

From `GET /admin/health` / metrics health object:

- [ ] `database_size_bytes` / `database_size_mb`
- [ ] `queue_health`
- [ ] `failed_jobs`
- [ ] `last_successful_crawl`
- [ ] `ai_processing_status`

---

## 4. Manual browser tests

Start API (section 1.5), then open Chrome/Firefox.

| # | Steps | Expected UI | P/F |
|---|-------|-------------|-----|
| 4.1 | Open `/admin/monitoring` **without** token | Error / unauthorized (not the dashboard) | ☐ |
| 4.2 | Open `/admin/monitoring?token=dev-admin-token` | Dark ops page: metric cards + tables for Running / Completed / Failed crawls | ☐ |
| 4.3 | Confirm cards visible | Running, Completed, Failed, Reviews today, Pending AI, AI queue, Branches processed, Avg duration, Avg reviews/branch | ☐ |
| 4.4 | Nav links work | “System Health” and “Metrics JSON” links navigate with token preserved | ☐ |
| 4.5 | Open `/admin/health?token=dev-admin-token` | Status badge (ok/attention/busy), DB size, queue, failed jobs, last successful crawl, pending AI | ☐ |
| 4.6 | Open `/demo` | Demo search UI still works (unchanged product surface) | ☐ |
| 4.7 | Open `/docs` | OpenAPI lists admin routes under tag `admin` | ☐ |
| 4.8 | Mobile width (~375px) | Admin pages readable; cards stack; no horizontal breakage blocking content | ☐ |
| 4.9 | After seeding + optional crawl | Monitoring tables show real run rows (not only “None”) | ☐ |

---

## 5. Edge cases

| # | Scenario | How to test | Expected | P/F |
|---|----------|-------------|----------|-----|
| 5.1 | Empty DB | Fresh `DB_PATH`, open admin pages | 200; zeros / empty tables; no 500 | ☐ |
| 5.2 | Duplicate import | Re-run upsert/crawl with same external IDs (or ops test) | Review count unchanged; duplicate_rate gauge sensible | ☐ |
| 5.3 | Interrupted crawl | Kill mid-run or use failing source (covered by `test_interrupt_and_retry_failed`) | Run `failed`/`interrupted`; retry resets tasks | ☐ |
| 5.4 | Token via query vs header | Both auth methods | Both 200 | ☐ |
| 5.5 | Extremely long company name in crawl list | Insert crawl_run with long name | HTML escapes; no XSS / broken layout crash | ☐ |
| 5.6 | `LOG_JSON=true` | Restart API with JSON logs | Startup log is JSON with `component`/`message` | ☐ |
| 5.7 | Staging profile | `BRANDMONITOR_ENV=staging` | Default DB path staging; JSON logging on | ☐ |
| 5.8 | Metrics after crawl | Hit metrics.json after stress/crawl | Non-zero counters/gauges when activity occurred in-process | ☐ |
| 5.9 | Public health vs admin health | Compare `/health` vs `/admin/health` | Public contract unchanged; admin is HTML ops page | ☐ |
| 5.10 | Export empty-ish DB | Backup with only companies | Files created; CSV headers present | ☐ |

---

## 6. Failure scenarios

| # | Failure | How to induce | Expected handling | P/F |
|---|---------|---------------|-------------------|-----|
| 6.1 | Missing admin token | Call `/admin/*` bare | **401** `unauthorized`; no stack trace HTML | ☐ |
| 6.2 | Wrong admin token | `?token=nope` | **401** | ☐ |
| 6.3 | Production without `ADMIN_TOKEN` | Load settings in prod env | Startup/config **refuses** to load | ☐ |
| 6.4 | DB missing path parent | Use nested new `DB_PATH` | API/crawl creates parent dirs or fails clearly | ☐ |
| 6.5 | Backup missing DB file | `backup_export.py --db /tmp/missing.db` | Non-zero exit: `Database not found` | ☐ |
| 6.6 | Branch crawl hard-fail | Simulated in unit test / flaky source | Task `failed`; scheduler `retry-failed` can re-queue | ☐ |
| 6.7 | Unhandled API exception | (If injectable) invalid internal path | **500** JSON `internal_error`; logged; no raw traceback to client | ☐ |
| 6.8 | Invalid Maps blocked (optional live) | Run live crawl from datacenter IP | Documented limited-view: branches may work, reviews empty — **must not crash** process | ☐ |
| 6.9 | Concurrent API workers on SQLite | *(Do not ship)* `--workers 2` | Known risk; QA notes “workers must be 1” — mark **N/A** unless testing warning | ☐ N/A |

---

## 7. Screenshots I should expect

Capture and attach to the QA ticket / PR. Filenames suggested:

| # | Screenshot | What it must show | File name | P/F |
|---|------------|-------------------|-----------|-----|
| 7.1 | Admin monitoring | Cards + three crawl tables | `qa_admin_monitoring.png` | ☐ |
| 7.2 | Admin system health | Status + DB size + queue + failed jobs | `qa_admin_health.png` | ☐ |
| 7.3 | Admin unauthorized | 401 / error when token missing | `qa_admin_unauthorized.png` | ☐ |
| 7.4 | Metrics JSON | Browser or jq output of `metrics`+`health` keys | `qa_admin_metrics.png` | ☐ |
| 7.5 | Public health | `/health` JSON `status=ok` | `qa_public_health.png` | ☐ |
| 7.6 | Demo still works | `/demo` first screen (regression) | `qa_demo_regression.png` | ☐ |
| 7.7 | Pytest green | Terminal: `32 passed` (or full suite green) | `qa_pytest_green.png` | ☐ |
| 7.8 | Stress output | Terminal lines `STRESS_50K` + `STRESS_1K_BRANCHES` | `qa_stress_output.png` | ☐ |
| 7.9 | Backup artifacts | Finder/tree of `backups/...` with db/csv/json | `qa_backup_artifacts.png` | ☐ |

---

## 8. Pass / Fail criteria

### Feature PASS (all required)

Phase 5 is **PASS** only if:

1. **All automated tests pass** — full `pytest tests/` green (including Phase 5 ops + stress).  
2. **All admin auth tests pass** — no token / wrong token → 401; valid token → 200.  
3. **Admin monitoring + health pages load** in browser with required fields visible.  
4. **Public API contracts unchanged** — `/health`, `/companies`, `/search`, `/demo` still 200 with prior shapes.  
5. **Config profiles work** — dev/staging load; production requires `ADMIN_TOKEN`.  
6. **Backup/export produces** SQLite + CSV + JSON artifacts.  
7. **Stress gates met** — 50k reviews and 1k branches tests pass under time limits.  
8. **Interrupt + duplicate scenarios pass** (automated ops tests).  
9. **Screenshots 7.1–7.9 captured** (or explicitly waived in writing by PM).  
10. **No Sev-1/Sev-2 defects** open against Phase 5 scope.

### Feature FAIL (blockers)

Mark **FAIL** / incomplete if any of:

- Any Phase 5 test fails or is skipped without waiver  
- Admin routes accessible without token  
- Admin pages 500 on empty or seeded DB  
- Public `/health` or demo broken  
- Production settings allow empty admin token  
- Backup command crashes or writes empty/corrupt required files  
- Stress tests timeout or wrong counts  
- Scoring / demo UI / public response schemas changed unintentionally  

### Sign-off

| Role | Name | Date | Verdict |
|------|------|------|---------|
| QA Engineer | | | PASS / FAIL |
| Dev owner | | | |
| Notes / defects | | | |

```text
VERDICT: ☐ PASS   ☐ FAIL — Phase 5 NOT complete until PASS
```

---

## Quick copy-paste QA script

```bash
export BRANDMONITOR_ENV=development
export ADMIN_TOKEN=dev-admin-token
export DB_PATH=data/qa_brandmonitor.db
export PYTHONPATH=.

python3 -m pytest tests/ -q
python3 scripts/seed_demo_data.py || true
python3 scripts/backup_export.py --db "$DB_PATH" --out-dir backups/qa --format all

# terminal 1
uvicorn api.main:app --host 127.0.0.1 --port 8000 --workers 1

# terminal 2
curl -sS -o /dev/null -w "health:%{http_code}\n" http://127.0.0.1:8000/health
curl -sS -o /dev/null -w "admin_no_token:%{http_code}\n" http://127.0.0.1:8000/admin/monitoring
curl -sS -o /dev/null -w "admin_ok:%{http_code}\n" \
  "http://127.0.0.1:8000/admin/monitoring?token=$ADMIN_TOKEN"
curl -sS -o /dev/null -w "admin_health:%{http_code}\n" \
  "http://127.0.0.1:8000/admin/health?token=$ADMIN_TOKEN"
```

Open in browser:

- http://127.0.0.1:8000/admin/monitoring?token=dev-admin-token  
- http://127.0.0.1:8000/admin/health?token=dev-admin-token  
- http://127.0.0.1:8000/demo  
- http://127.0.0.1:8000/health  
