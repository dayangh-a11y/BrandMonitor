# Race Intelligence

Post-race card answering: how hard was the race, how wrong was the market
(rating proxy), who shocked / was overrated / underrated, and how
confident a pre-race call should have been.

## Card fields

```
Race Intelligence

Difficulty:
★★★★★

Crowd Accuracy:
18%

Biggest Surprise:
اسب X

Most Overrated Horse:
اسب Y

Most Underrated Horse:
اسب Z

Shock Score:
96/100

Prediction Confidence:
Low
```

| Field | Meaning |
|-------|---------|
| Difficulty | 1–5 stars from field size + rating tightness (+ class boost) |
| Crowd Accuracy | Spearman of expected vs finish ranks → 0–100% |
| Biggest Surprise | Largest positive residual (`expected_rank − finish`) |
| Most Overrated | Top-half expectation, worst residual |
| Most Underrated | Bottom-half expectation, best residual |
| Shock Score | Favorite finish + winner’s expected rank + inverted crowd accuracy |
| Prediction Confidence | High / Medium / Low from rating gap vs shock |

## Expectation source

Warehouse `wh_race_results.odds` is typically NULL. Pre-race expectation
uses **`source_rating`** (entrance / published rating). Higher rating ⇒
better expected finish. Stored as `expectation_source`: `rating` | `mixed` | `none`.

## Persistence

| Table / view | Role |
|--------------|------|
| `anl_race_intelligence` | One row per race with `report_text`, `explain_json`, `runners_json` |
| `anl_v_race_intelligence` | Convenience projection |
| `anl_v_high_shock_races` | Shock ≥ 70 |

Built automatically inside `analytics build`, or standalone:

```bash
python main.py analytics race-intel --rebuild --course gonbad-kavous
python main.py analytics race-intel --race-id 123
python main.py analytics race-intel --shockiest -n 5
```

## Layer placement

```
wh_races + wh_race_results  →  compute_race_intelligence  →  anl_race_intelligence
```

Does not write Raw or Feature tables.
