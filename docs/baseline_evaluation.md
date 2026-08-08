# Baseline Evaluation + Dataset Freeze

## Freeze

```bash
python scripts/freeze_and_evaluate_baselines.py --version pf-v1.0.0-20260808
```

Creates immutable metadata under `data/prediction_foundation/freezes/`:

- dataset version, timestamps
- dataset sha256 (evaluation refuses mismatch)
- source DB sha256
- feature dictionary sha256
- observation / horse / race / split counts

## Evaluate baselines (TEST only, race-level)

Baselines:

| ID | Name |
|----|------|
| A | Historical Ranking |
| B | Current Race Rating (`source_rating`, pre-race) |
| C | Recent Form |
| D | Contextual Ranking |

Outputs:

- `data/prediction_foundation/baseline_eval/baseline_metrics.json`
- `data/prediction_foundation/baseline_eval/baseline_race_results.jsonl`
- `data/prediction_foundation/baseline_eval/baseline_failure_analysis.json`
- `data/prediction_foundation/baseline_eval/baseline_report.md`
- `data/prediction_foundation/baseline_eval/PRE_RACE_BASELINE_BENCHMARK.txt`

Scores are **SCORE/RANK**, not probabilities. Brier/calibration are not computed.

## ML gate

If Contextual Ranking does not **materially** outperform A/B/C (Wilson CI / rank margin):

**DO_NOT_TRAIN_YET**
