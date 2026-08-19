# PRE-RACE BASELINE BENCHMARK

- Dataset version: `pf-v1.0.0-20260808`
- Dataset sha256: `f671acc534266451afb3812963b9cd49dfa8435a7f20092729700b6aa39e770c`
- Split: **TEST**
- TEST races (grouped): 640
- Probability/Brier: **not applicable** (SCORE/RANK only)
- ML status: **DO_NOT_TRAIN_YET**

## Comparison table

| Baseline | Winner Hit % | Winner Top3 % | Winner in Pred Top3 % | Mean Winner Rank | Median Winner Rank | MRR | NDCG@3 | N races |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A Historical Ranking | 16.45 | 41.85 | 42.49 | 4.907 | 4.0 | 0.3658 | 0.6144 | 626 |
| B Current Race Rating | 14.8 | 42.06 | 38.99 | 5.056 | 4.5 | 0.3478 | 0.6105 | 554 |
| C Recent Form | 16.72 | 39.87 | 40.19 | 4.995 | 4.0 | 0.3637 | 0.6013 | 622 |
| D Contextual Ranking | 14.69 | 36.56 | 41.88 | 4.802 | 4.0 | 0.3558 | 0.5838 | 640 |

**Best baseline:** A (Historical Ranking)
**Contextual outperforms simpler?** NO
**ML gate:** DO_NOT_TRAIN_YET

## Tradeoffs

- Historical Ranking is stable when careers are long but weak for debuts/recent improvers.
- Race Rating depends on source_rating coverage; many TEST rows lack rating.
- Recent Form reacts quickly but overfits tiny samples (n<3).
- Contextual Ranking blends signals but can still be dominated by sparse track/distance cells.

## Top 20 failures (best baseline)

1. race_id=2418 date=2025-10-10 field=14 winner_pred_rank=13 pred1_finish=14 coverage=MEDIUM
2. race_id=2499 date=2025-12-31 field=12 winner_pred_rank=12 pred1_finish=11 coverage=HIGH
3. race_id=1519 date=2026-05-06 field=13 winner_pred_rank=13 pred1_finish=10 coverage=HIGH
4. race_id=1364 date=2026-06-28 field=13 winner_pred_rank=13 pred1_finish=10 coverage=MEDIUM
5. race_id=2375 date=2025-05-14 field=12 winner_pred_rank=11 pred1_finish=11 coverage=MEDIUM
6. race_id=1611 date=2026-01-28 field=13 winner_pred_rank=13 pred1_finish=9 coverage=MEDIUM
7. race_id=1294 date=2026-07-30 field=12 winner_pred_rank=10 pred1_finish=12 coverage=HIGH
8. race_id=1697 date=2025-05-15 field=13 winner_pred_rank=12 pred1_finish=9 coverage=MEDIUM
9. race_id=1558 date=2026-02-07 field=13 winner_pred_rank=13 pred1_finish=8 coverage=MEDIUM
10. race_id=1379 date=2026-06-26 field=13 winner_pred_rank=10 pred1_finish=11 coverage=HIGH
11. race_id=1335 date=2026-07-16 field=13 winner_pred_rank=12 pred1_finish=9 coverage=HIGH
12. race_id=1292 date=2026-07-31 field=12 winner_pred_rank=10 pred1_finish=11 coverage=HIGH
13. race_id=787 date=2026-08-01 field=13 winner_pred_rank=12 pred1_finish=9 coverage=HIGH
14. race_id=771 date=2025-11-08 field=12 winner_pred_rank=10 pred1_finish=10 coverage=MEDIUM
15. race_id=1588 date=2026-02-03 field=13 winner_pred_rank=11 pred1_finish=9 coverage=LOW
16. race_id=1370 date=2026-06-27 field=13 winner_pred_rank=10 pred1_finish=10 coverage=HIGH
17. race_id=1698 date=2025-04-30 field=12 winner_pred_rank=10 pred1_finish=9 coverage=HIGH
18. race_id=2396 date=2025-08-30 field=12 winner_pred_rank=12 pred1_finish=7 coverage=MEDIUM
19. race_id=2440 date=2025-11-28 field=13 winner_pred_rank=13 pred1_finish=6 coverage=LOW
20. race_id=2474 date=2025-12-26 field=13 winner_pred_rank=13 pred1_finish=6 coverage=MEDIUM
