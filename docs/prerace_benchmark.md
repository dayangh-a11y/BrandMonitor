# Pre-Race Benchmark (Immutable)

A **Pre-Race Benchmark** freezes a ranking snapshot before the race runs.

## Rules

1. **Immutable / write-once** — do not overwrite after freeze (SHA-256 guarded).
2. **No future data** — `data_cutoff_utc` is the hard cutoff; later publications must not alter the snapshot.
3. **Do not change the frozen ranking scores** at freeze time.
4. **No Prediction Probability** — Relative Score Share is **not** a probability.
5. **Evaluation is separate** — post-race metrics are written to a different file.

## Freeze (Mashhad Week 2 / 1000m)

```bash
python scripts/freeze_prerace_benchmark.py
```

Artifact:

- `data/prerace/benchmarks/mashhad_week2_turkmen_1000m_2026-08-08.json`
- sidecar: `*.json.immutable`

Frozen horse fields:

`horse_id`, `horse`, `final_score`, `rank`, `confidence`,
`historical_score`, `recent_form_score`, `track_score`, `distance_score`, `rating_score`

Leans (separate):

- `WIN_LEAN`
- `EXACTA_LEAN`
- `TOP_3`

## Evaluate after the race

```bash
python scripts/evaluate_prerace_benchmark.py \
  --benchmark data/prerace/benchmarks/mashhad_week2_turkmen_1000m_2026-08-08.json \
  --actual-json path/to/actual_finish.json \
  --out data/prerace/evaluations/eval_mashhad_week2.json
```

`actual_finish.json` example:

```json
{
  "race_id": null,
  "finish_order": [
    {"horse_id": 6348, "finish_position": 1},
    {"horse_id": 6323, "finish_position": 2}
  ]
}
```

Metrics:

| Metric | When |
|--------|------|
| Winner Hit | always |
| Top 2 Hit | always |
| Top 3 Hit | always |
| Exacta Hit | always |
| Rank correlation (Spearman) | always |
| Brier Score | only if real probabilities exist |
| Calibration | only if real probabilities exist |

Relative Score Share is never used as Probability.
