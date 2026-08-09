# Prediction Foundation / Feature Engineering

Phase goal: leakage-safe **horse × race** feature dataset.

**Not in this phase:** ML training, betting features, DB mutation, future-result leakage.

## Unit

One observation = **ONE HORSE × ONE RACE**, with features computed from information
available **strictly before** `race_date`.

## Build

```bash
python scripts/build_prediction_features.py
python scripts/build_prediction_features.py --max-rows 2000  # smoke
```

Outputs:

- `data/prediction_foundation/reports/feature_dictionary.json`
- `data/prediction_foundation/reports/coverage_report.json`
- `data/prediction_foundation/reports/observation_counts.json`
- `data/prediction_foundation/reports/leakage_audit.json`
- `data/prediction_foundation/reports/baselines.json`
- `data/prediction_foundation/reports/readiness.json`
- `data/prediction_foundation/datasets/observations.jsonl.gz`
- `data/prediction_foundation/datasets/observations_sample.csv`

## Rules

| Rule | Enforcement |
|------|-------------|
| Time cutoff `prior.race_date < current` | `build_observations` append-after-compute |
| Targets isolated | `compute_targets` separate from `compute_features` |
| Missing ≠ zero | `FeatureCell(is_missing=...)` |
| Sample size | every contextual family exposes `*_sample_n` |
| Shrinkage | EB smoothed rates + raw_rate |
| Class | structured only; never invent from free text |
| Splits | chronological 70/15/15 |
| Baselines A–D | defined, not trained |
| ML | **DO NOT TRAIN YET** |

## Package

`src/prediction_foundation/` — `types`, `dictionary`, `compute`, `build`, `split`,
`shrinkage`, `leakage`, `baselines`, `readiness`
