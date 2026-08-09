# Phase 7 — API Readiness

- HTTP server: **not implemented** (contract only)
- Engine functions: **available** (`src/prediction_engine`)
- Telegram: must remain a thin client of this API/engine

## Required operations

- `GET /race/{race_id}`
- `GET /race/{race_id}/ranking`
- `GET /horse/{horse_id}`
- `GET /horse/{horse_id}/form`
- `GET /horse/{horse_id}/pedigree`
- `GET /horse/{horse_id}/track-record`
- `GET /horse/{horse_id}/distance-record`
- `GET /horse/{horse_id}/analysis`
