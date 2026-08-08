# Prediction Foundation Report

## Observation counts

- horse×race observations: **32970**
- unique permanent horses: **9411**
- races: **3317**
- tracks: **9**
- trainers: **1117**
- date range: 1994-05-20 → 2026-08-07
- splits: `{'TRAIN': 22199, 'VALIDATION': 3944, 'TEST': 6827}`

## Readiness

**Can we create a leakage-safe training dataset?** **YES**

### Blockers
- none

### Warnings
- Leakage risk MEDIUM — classification may be backfilled after race publication; freeze class as-of snapshot recommended on feature starts_same_class
- Leakage risk MEDIUM (same as class source) on feature wins_same_class
- Leakage risk MEDIUM on feature top3_same_class
- Leakage risk MEDIUM on feature avg_finish_same_class
- Leakage risk MEDIUM on feature class_win_rate
- Leakage risk MEDIUM on feature class_top3_rate
- Leakage risk MEDIUM on feature class_sample_n
- Leakage risk MEDIUM — backfill risk on feature race_class
- Leakage risk MEDIUM on feature age_category
- Leakage risk MEDIUM — post-scratch final field may differ from morning declaration on feature field_size
- Structured class available on only 12.9% of observations — class features mostly missing (not invented; not a leakage blocker)
- Class feature family is too sparse for class-conditioned models; baselines A/C/D without class remain usable

## Leakage audit (MEDIUM+ features)

- `starts_same_class` — MEDIUM — classification may be backfilled after race publication; freeze class as-of snapshot recommended
- `wins_same_class` — MEDIUM (same as class source)
- `top3_same_class` — MEDIUM
- `avg_finish_same_class` — MEDIUM
- `class_win_rate` — MEDIUM
- `class_top3_rate` — MEDIUM
- `class_sample_n` — MEDIUM
- `race_class` — MEDIUM — backfill risk
- `age_category` — MEDIUM
- `field_size` — MEDIUM — post-scratch final field may differ from morning declaration

## Coverage (selected)

| Feature | Available % | Missing % | Reliable % |
|---|---:|---:|---:|
| career_win_rate | 71.41 | 28.59 | 24.25 |
| avg_finish_last5 | 65.53 | 34.47 | 11.22 |
| win_rate_same_distance | 43.94 | 56.06 | 4.17 |
| track_win_rate | 55.14 | 44.86 | 10.97 |
| class_win_rate | 2.19 | 97.81 | 0.01 |
| trainer_win_rate_prior | 95.26 | 4.74 | 85.53 |
| owner_win_rate_prior | 22.33 | 77.67 | 22.33 |
| race_class | 12.89 | 87.11 | 12.89 |
| assigned_weight | 70.12 | 29.88 | 70.12 |
| field_size | 100.0 | 0.0 | 100.0 |

## Policy

- DB not modified
- ML not trained
- Betting data not used
- Targets isolated from features
- Chronological splits only

