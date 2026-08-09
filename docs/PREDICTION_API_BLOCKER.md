# Prediction HTTP API — Status

**Status:** PATH 1 implemented (freeze-backed API)  
**Branch:** `cursor/prediction-api-layer-c27a`  
**Dataset freeze:** `pf-v1.0.0-20260808`  
**ML gate (unchanged):** `DO_NOT_TRAIN_YET`

## Modes

| Mode | How | Dataset |
|------|-----|---------|
| **Production** | `PREDICTION_VERIFY_FREEZE=true` (default) | Must be `data/prediction_foundation/datasets/observations.jsonl.gz` matching freeze sha256. Startup **fails** if missing. Test fixture is refused. |
| **Fixture/test** | `PREDICTION_VERIFY_FREEZE=false` + fixture path | `tests/fixtures/prediction_api/observations_fixture.jsonl.gz` for tests/smoke only. |

There is **no** silent fallback from production → fixture.

## Canonical search result

`observations.jsonl.gz` was **not** found elsewhere in the workspace, artifacts, or repo.
Only the freeze metadata and the API test fixture exist. The production path remains gitignored
(`.gitignore`: `data/prediction_foundation/datasets/*.jsonl.gz`).

Expected sha256 (from freeze): `f671acc534266451afb3812963b9cd49dfa8435a7f20092729700b6aa39e770c`

## What shipped

- `src/prediction_engine/` — façade over existing `baseline_eval.rank_race`
- `src/api/` — FastAPI app (`uvicorn src.api.main:app`)
- Endpoints: `/health`, `/races/{id}`, `/races/{id}/prediction`, `/horses/{id}`
- `probability` always `null`

## Fixture smoke

```bash
PREDICTION_DATASET_PATH=tests/fixtures/prediction_api/observations_fixture.jsonl.gz
PREDICTION_VERIFY_FREEZE=false
uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```
