# NIGHT RUN FINAL REPORT

- Generated (UTC): `2026-08-08T22:59:38.313171+00:00`
- Final system status: **`FOUNDATION_READY_FOR_TELEGRAM_WIRING`**

## Gate summary

| Gate | Value |
|------|-------|
| READY_FOR_TELEGRAM | **YES** |
| READY_FOR_ML | **NO** |
| PEDIGREE_READY | **YES** |
| BASELINE_VALIDATED | **YES** |
| ML STATUS | **`DO_NOT_TRAIN`** |

## 1. Pedigree coverage

- Canonical horses: 9414
- Sire coverage: 99.522%
- Dam coverage: 96.6964%
- Complete (both): 96.5158%
- Entities: sire=1251, dam=5145

## 2. Pedigree conflicts

- Count: 19
- Auto-resolved: **no**

## 3. Data quality status

- Overall: **WARNINGS**
- High-severity anomaly groups: 2
- Critical coverage gaps: []

## 4. Feature coverage

- Dataset: `pf-v1.0.0-20260808`
- SHA256: `f671acc534266451afb3812963b9cd49dfa8435a7f20092729700b6aa39e770c`
- Pedigree in feature freeze: **False**

## 5. Leakage status

- Leakage audit passed: **True**
- Cutoff: `(race_date, race_id, result_id)`
- Betting data: unused

## 6. Dataset size

- See `phase3_prediction_dataset/prediction_dataset_version.json` and PF freeze counts
- Warehouse results underpin baselines (~32,970 horse×race observations in PF freeze)

## 7. Baseline results

- Best baseline: **A Historical Ranking**
- Winner hit: 16.45%
- Actual winner in predicted top3: 42.49%
- Mean winner rank: 4.907
- MRR: 0.3658
- NDCG@3: 0.6144
- N races: 626

## 8. Best baseline

**A — Historical Ranking**

## 9. ML recommendation

- Gate answer: **NO**
- Recommendation: **`DO_NOT_TRAIN`** (trained=False)
- Do not train until Contextual materially beats A/B/C with clear CI separation.

## 10. Prediction engine readiness

- Contract version smoke: **True**
- Sample race_id: `3393`
- Score ≠ probability

## 11. API readiness

- Contract ready: **True**
- HTTP implemented: **False**

## 12. Telegram readiness

- Design ready: **True**
- Bot implemented: **False**
- READY_FOR_TELEGRAM means engine+API contract+design are wire-ready, not that a bot ships today.

## 13. Remaining blockers

- Pedigree not yet in prediction feature freeze (file foundation ready; needs next PF rebuild after migration review)
- Data quality status=WARNINGS — review anomalies
- ML gate closed — contextual baseline does not materially beat simpler
- HTTP API server not implemented (contract only)
- Telegram bot UI not implemented (by design in this run)

## 14. Recommended next action

1. Review pedigree migration proposal; load harvest into DB after approval.
2. Rebuild prediction features including pedigree (as-of offspring only).
3. Implement thin HTTP API wrapping `src/prediction_engine`.
4. Implement Telegram bot as pure presentation client.
5. Keep ML gated (`DO_NOT_TRAIN`) until Contextual clearly wins.

## Phase statuses

| Phase | Status |
|------|--------|
| 1 Pedigree | COMPLETE |
| 2 Data quality | COMPLETE |
| 3 Dataset validation | COMPLETE_WITH_WARNINGS |
| 4 Baselines | COMPLETE |
| 5 ML gate | COMPLETE |
| 6 Engine contract | COMPLETE |
| 7 API readiness | COMPLETE |
| 8 Telegram design | COMPLETE |

## Artifacts root

`data/night_run/`
