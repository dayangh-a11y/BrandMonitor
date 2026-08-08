# Phase 3 — Prediction Dataset Validation

- Dataset: `pf-v1.0.0-20260808`
- SHA256: `f671acc534266451afb3812963b9cd49dfa8435a7f20092729700b6aa39e770c`
- Leakage audit passed: **True**
- Unit: horse × race; cutoff `(race_date, race_id, result_id)`
- Betting data: NOT USED

## Feature groups

- HORSE_HISTORY: NO/PARTIAL — Not detected in feature dictionary tokens
- RECENT_FORM: NO/PARTIAL — Not detected in feature dictionary tokens
- DISTANCE: NO/PARTIAL — Not detected in feature dictionary tokens
- TRACK: NO/PARTIAL — Not detected in feature dictionary tokens
- CLASS: NO/PARTIAL — Not detected in feature dictionary tokens
- BREED: NO/PARTIAL — Not detected in feature dictionary tokens
- TRAINER: NO/PARTIAL — Not detected in feature dictionary tokens
- OWNER: NO/PARTIAL — Not detected in feature dictionary tokens
- WEIGHT: NO/PARTIAL — Not detected in feature dictionary tokens
- FIELD_SIZE: NO/PARTIAL — Not detected in feature dictionary tokens
- PEDIGREE: NO/PARTIAL — PEDIGREE features not yet in PF freeze — pedigree foundation is file-ready for next feature rebuild

## Notes

- Missing values must remain `is_missing` (never zero-filled).
- Rates keep sample_n + reliability bands.
- Pedigree can be joined in a future dataset version after DB migration review.
