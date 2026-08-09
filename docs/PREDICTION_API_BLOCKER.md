# Prediction HTTP API — Blocker Report

**Status:** STOPPED (no API implementation in this change)  
**Branch intent:** `cursor/prediction-api-layer-c27a`  
**Dataset freeze referenced by task:** `pf-v1.0.0-20260808`  
**ML gate (unchanged):** `DO_NOT_TRAIN_YET`

## Why work stopped

The task requires an HTTP layer on top of an **existing** package:

- `src/prediction_engine`
- `rank_race(...)`
- `get_horse_analysis(...)`

Those symbols **do not exist** in this repository (current tree or reachable feature branches for the horse-racing collector).

Per task critical rule:

> If you discover that the existing prediction engine cannot safely be called from an HTTP request without changing its internals, STOP and explain the exact blocker instead of rewriting the engine.

Implementing the requested API would require **inventing** a new `prediction_engine` façade or **rewiring** scoring call paths. That violates the non-rewrite / non-rescore constraints.

---

## What exists instead

### A) Offline baseline scorer (SCORE-only — matches API contract philosophy)

| Item | Location |
|------|----------|
| Function | `src/prediction_foundation/baseline_eval.py::rank_race` |
| Signature | `rank_race(horses: list[dict], scorer: Callable) -> list[dict]` |
| Output | `pred_score`, `pred_rank` only — **no probability** |
| Baseline A metrics (TEST) | winner hit **16.45%**; actual winner in pred Top-3 **42.49%** |
| Freeze | `data/prediction_foundation/freezes/pf-v1.0.0-20260808.json` |

**Why it cannot back `GET /races/{race_id}/prediction` safely today:**

1. It ranks a **pre-built list of frozen feature rows**, not a live warehouse `race_id`.
2. Frozen observations file `data/prediction_foundation/datasets/observations.jsonl.gz` is **gitignored / absent** in this environment (`LATEST.json` points at it; file not present).
3. Historical SQLite `output/historical/horse_racing.db` is also **absent** (needed to rebuild observations).
4. There is **no** `get_horse_analysis` in this module.

### B) Live pre-race engine (race_id-capable — different contract)

| Item | Location |
|------|----------|
| Entry | `src/prerace/engine.py::build_prerace_report(session, race_id, *, persist=True, ...)` |
| Field load | `src/markets/context.py::load_field_for_race` |
| Per-horse score | `todays_chance_score` plus **`winning_probability` / top2 / top3** (softmax) |

**Why it is not a drop-in for this task’s API schema:**

1. Task states the current engine produces **SCORE, not probability**, and the response must keep `"probability": null` without fabricating.
2. Pre-race engine **already emits probabilities**. Exposing them would change the stated contract; forcing `null` would hide engine output and invite confusion with “don’t invent probability”.
3. Default `persist=True` writes `anl_prerace_reports` — HTTP read path would need `persist=False` (safe, but still a wrapper decision).
4. Still **no** `get_horse_analysis(horse_id)` — only whole-race reports / field scoring.
5. Needs a populated warehouse DB session; DB is missing here.

### C) HTTP stack

- No FastAPI/Flask/Starlette/Django in `pyproject.toml` / `requirements.txt`.
- Remote `phase3-rest-api-a9ca` is an unrelated BrandMonitor API, not this engine.

---

## Exact blockers (checklist)

1. **Missing package:** `src/prediction_engine/` not in repo.  
2. **Missing function:** `get_horse_analysis` not defined anywhere.  
3. **Wrong `rank_race` shape:** only offline feature-row ranking exists; not `rank_race(race_id)`.  
4. **Missing freeze body:** `observations.jsonl.gz` not available in workspace.  
5. **Missing live DB:** `output/historical/horse_racing.db` not available for warehouse-backed race/horse endpoints.  
6. **Contract mismatch:** live prerace emits probabilities; task API forbids treating score as probability and expects `probability: null`.

---

## Safe next steps (out of scope unless approved)

Do **one** of the following explicitly before implementing the HTTP API:

**Option 1 — Freeze-backed prediction API (closest to baseline SCORE contract)**  
- Restore `observations.jsonl.gz` (or allow rebuild from DB without mutating freeze metadata).  
- Add a thin read-only adapter (new package name agreed by owners) that:
  - loads frozen rows by `race_id`
  - calls existing `rank_race` + baseline scorers unchanged
  - returns `score` / `rank` with `probability: null`
- Horse analysis would need a **new** read-only aggregator (not present today) — define its contract first.

**Option 2 — Live prerace API (different product contract)**  
- Confirm owners accept exposing prerace `winning_probability` (or a separate field name), **or** accept a response that returns score-only and documents that prerace probs are intentionally omitted (not null-washed as “no model”).  
- Wire FastAPI → `build_prerace_report(..., persist=False)` without changing `src/prerace` scoring.  
- Define `GET /horses/{id}` as filtered race analysis or a new non-scoring profile endpoint.

**Option 3 — Introduce `src/prediction_engine` as the public façade**  
- Only after product sign-off that this is an **adapter layer**, not a scoring rewrite.  
- Map clearly to either Option 1 or 2; keep ML gate `DO_NOT_TRAIN_YET`.

---

## What was intentionally not done

- No FastAPI app / endpoints  
- No new ML / probability calibration  
- No freeze mutation  
- No prerace/baseline scoring changes  
- No Telegram bot  
- No pedigree migration  

## Environment notes confirming freeze identity

From `data/prediction_foundation/baseline_eval/baseline_metrics.json`:

- `dataset_version`: `pf-v1.0.0-20260808`
- Baseline A: `winner_hit_pct` 16.45; `actual_winner_in_pred_top3_pct` 42.49
- `probability_calibration`: `NOT_APPLICABLE — baselines produce SCORE/RANK only`
