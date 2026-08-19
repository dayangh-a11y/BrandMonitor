# Prediction Market Analytics

Treats **مشارکت مردمی** (`mosharekat.asbdavani.app`) as a prediction market and
compares crowd / pool expectations with official race outcomes.

## Quick start

```bash
python main.py init-db
python main.py prediction discover
python main.py prediction collect                 # all public historical days
python main.py prediction collect --limit-days 5  # sample
python main.py prediction build
python main.py prediction query -q most_surprising -n 10
python main.py prediction query -q biggest_upset
python main.py prediction query -q most_overrated
python main.py prediction query -q trainer_beats_market
```

## Architecture

```
api-mosharekat  →  raw_prediction_snapshots  →  wh_prediction_*  →  anl_prediction_*  →  views
```

| Table | Role |
|-------|------|
| `raw_prediction_snapshots` | Append-only JSON (racecard / odds / survey / days) |
| `wh_prediction_events` | PredictionEvents — one row per mosharekat race |
| `wh_prediction_entries` | PredictionEntries — per-horse market/survey signal |
| `wh_prediction_statistics` | PredictionStatistics — distribution summary |
| `wh_prediction_rewards` | PredictionRewards — pools / prize pools |
| `wh_prediction_winners` | PredictionWinners — official ranks + pool winners |
| `anl_prediction_race_metrics` | Race-level analytics + ML features |
| `anl_prediction_entity_metrics` | Horse / trainer / jockey / owner / sire metrics |

## Data sources (discovered)

See [`DISCOVERY.md`](prediction_market/DISCOVERY.md) and
[`discovered_fields.json`](prediction_market/discovered_fields.json).

Public (no auth):

- `GET /api/v1/races/days?limit=500`
- `GET /api/v1/races/racecard?day_id=`
- `GET /api/v1/pools/race/{id}/odds`
- `GET /api/v1/races/{id}/survey-statistics`

Auth-required (individual user bets): `/api/v1/bets`, `/bets/summary`, admin pick-charts.
Public history therefore stores **aggregated** market entries (odds + survey votes),
not per-user tickets, unless credentials are provided later.

Pre-race snapshots: when a race `status` is `OPEN`, snapshots are flagged
`is_pre_race=true`. Closed days still retain the latest odds/survey payload
(historical closing market).

## Natural language questions

| Question | CLI `-q` |
|----------|----------|
| Most surprising horse | `most_surprising` |
| Biggest upset | `biggest_upset` |
| Most overrated / underrated | `most_overrated` / `most_underrated` |
| Outperform public / disappoint | `outperform_public` / `disappoint` |
| Hardest / easiest race to predict | `hardest_race` / `easiest_race` |
| Trainer beats market | `trainer_beats_market` |
| Underestimated jockey | `jockey_underestimated` |
| Unpredictable sire | `sire_unpredictable` |

## Dashboard views

- `anl_v_pred_top_surprises`
- `anl_v_pred_most_overrated` / `_underrated`
- `anl_v_pred_most_predictable` / `_least_predictable`
- `anl_v_pred_accuracy_timeline`
- `anl_v_pred_crowd_intelligence`
- `anl_v_pred_race_shock`
- `anl_v_pred_ml_features`

## Metric math

Full formulas: [`METRICS.md`](prediction_market/METRICS.md).
