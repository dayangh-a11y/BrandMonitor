# Analytics Layer (`anl_*`)

Standardized horse-racing performance metrics and instant ranking views.

Designed after common international handicapping concepts (form windows,
consistency, relative speed vs field, opponent quality, earnings indices)
while remaining rebuildable from the warehouse.

## Layer placement

```
raw_*  →  wh_*  →  feat_* (optional weather)  →  anl_*  →  anl_v_* views
```

| Prefix | Role |
|--------|------|
| `anl_seasons` | Inferred season clusters from race dates |
| `anl_horse_metrics` | Flat ML-ready metric row per horse × scope |
| `anl_rankings` | Leaderboards with `why_text` / `why_json` |
| `anl_race_intelligence` | Per-race surprise / crowd / shock cards |
| `anl_v_*` | SQL views for instant questions |

Analytics **never** writes Raw.

## CLI

```bash
python main.py init-db
python main.py analytics build [--course gonbad-kavous] [--top 25]
python main.py analytics query -q best_season -n 10
python main.py analytics query -q best_turkmen
python main.py analytics query -q best_trainer
python main.py analytics race-intel --race-id 123
python main.py analytics race-intel --shockiest -n 5
```

See also [`docs/race_intelligence.md`](race_intelligence.md).

## Horse metrics (every row)

| Metric | Meaning |
|--------|---------|
| Performance Rating | Composite 0–100 (win/place/avg finish/consistency/speed/earnings/difficulty) |
| Consistency Score | Stability of finishing positions |
| Form Score 3/5/10 | Exponentially weighted recent form |
| Win / Place Rate | Standard rates |
| Avg Finish | Mean finishing position |
| Speed Index | Pace vs race field (100 ≈ average) |
| Earnings Index | Share of top earner in scope |
| Difficulty Index | Opponent quality + field size + class boost |
| Track / Distance / Weather / Going Preference | Best bucket + strength |
| Jockey / Trainer Combination Score | Best partnership strength |
| Fatigue Score | Turnaround + race density |
| Improvement / Decline Trend | Slope of recent form |
| Season / Career / Breed Ranking | Dense ranks inside scope |

Each metrics row stores `explain_text` + `explain_json` showing the components.

## Instant questions (views)

| Question | View |
|----------|------|
| Best horses this season | `anl_v_best_horses_season` |
| Most successful | `anl_v_most_successful_horses` |
| Most consistent | `anl_v_most_consistent_horses` |
| Best Turkmen / Do-Khoon / Thoroughbred | `anl_v_best_turkmen` / `_dokhoon` / `_thoroughbred` |
| Best trainer / jockey / owner / sire | `anl_v_best_*` |
| By distance / weather / track condition / class / age | `anl_v_best_by_*` |
| Improving / declining | `anl_v_improving_horses` / `anl_v_declining_horses` |
| Race intelligence / high shock | `anl_v_race_intelligence` / `anl_v_high_shock_races` |
| ML feature matrix | `anl_v_horse_metrics_ml` |

Example:

```sql
SELECT rank, horse, performance_rating, wins, win_rate, why_text
FROM anl_v_best_turkmen
WHERE scope = 'season'
ORDER BY rank
LIMIT 10;
```

## Season inference

No season column exists in source extracts. Seasons are clustered from
`wh_races.race_date` gaps per racecourse (same approach as historical
season reports). Latest completed cluster is flagged on `anl_seasons`.

## Extensibility for AI models

- `anl_horse_metrics` is one wide numeric row → join on `(horse_id, scope, season_key, breed)`
- `features_json` / `explain_json` hold nested detail without schema churn
- Rankings keep `metrics_json` so model training can use the same features that explain UI ranks
- Weather preferences light up after `weather attach` + `features build -p race_weather`

## Rebuild policy

`analytics build` deletes and recomputes `anl_*` tables, then recreates views.
Idempotent and safe to schedule after warehouse/weather refreshes.
