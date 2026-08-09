# Prediction HTTP API — Status

**Status:** PATH 1 implemented (freeze-backed API)  
**Branch:** `cursor/prediction-api-layer-c27a`  
**Dataset freeze:** `pf-v1.0.0-20260808`  
**ML gate (unchanged):** `DO_NOT_TRAIN_YET`

## What shipped

Thin read-only HTTP layer over existing offline baselines:

- `src/prediction_engine/` — façade over existing `baseline_eval.rank_race` (no scoring changes)
- `src/api/` — FastAPI app (`uvicorn src.api.main:app`)

Endpoints: `/health`, `/races/{id}`, `/races/{id}/prediction`, `/horses/{id}`

`probability` is always JSON `null`. SCORE is exposed as `score` only (never renamed or converted).

## Operational note

Full `data/prediction_foundation/datasets/observations.jsonl.gz` is gitignored and may be
absent in clean checkouts. Restore the file matching freeze sha256 for production
(`PREDICTION_VERIFY_FREEZE=true`).

Local tests/smoke use:

```bash
PREDICTION_DATASET_PATH=tests/fixtures/prediction_api/observations_fixture.jsonl.gz
PREDICTION_VERIFY_FREEZE=false
uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

## Earlier discovery (historical)

Before PATH 1, there was no `src/prediction_engine` package. The live prerace path emits
probabilities and was **not** used. Offline `rank_race` in
`src/prediction_foundation/baseline_eval.py` is the prediction source (SCORE/RANK only).
