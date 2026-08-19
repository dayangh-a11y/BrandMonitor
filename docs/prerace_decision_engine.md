# Pre-Race Decision Engine

**Goal:** the strongest pre-race decision engine for Iranian horse racing —  
not a historical statistics website.

## Input

Next week's race card + historical DB + horse/trainer/jockey history + weather +
track condition + rest days + distance/class/age/sex + field + H2H.

## Output

Complete **pre-race intelligence report** per race.

### Race level

Race Strength · Field Strength · Competition Level · Weather Impact ·  
Track Suitability · Expected Pace · Race Shape

### Horse level

Today's Chance Score · Win / Top2 / Top3 probs · H2H probs ·  
Distance / Track / Weather suitability · Form · Momentum · Consistency ·  
Risk · Reliability · Fatigue · Rest · Trainer/Jockey form & combos ·  
Opponent difficulty · Expected finish · Confidence

### Reports

Best Win / Place / H2H / Value · Most Under/Overrated · Dark Horse ·  
High Risk · Most Reliable · Most Improved · Best Long Shot

### Explainability

Every recommendation includes **why**, **metrics contributed**, **confidence**,  
**sample size**, **data quality**.

### Self-validation

Before publish: missing data, conflicting signals, low confidence,  
insufficient sample — **warn**; never fabricate. Empty field → blocked.

## CLI

```bash
python main.py prerace report --race-id 789
python main.py prerace card --course gonbad-kavous --date 2026-08-01
python main.py prerace card --course gonbad-kavous -n 8
```

## Package

`src/prerace/` — `engine.py`, `race_score.py`, `horse_score.py`, `reports.py`,  
`validate.py`, `report.py`, `models.py` (`anl_prerace_reports`)
