# Sex Normalization Engine

Biological sex is normalized for every horse and every race. Season
comparisons use **Sex Adjusted Performance Rating** so mares are not
penalized for racing stronger male fields.

## Sex labels

| Label | Group | Source mapping |
|-------|-------|----------------|
| Colt | male | نر / male, age &lt; 5 |
| Stallion | male | نر / male, age ≥ 5 (default if age unknown) |
| Gelding | male | اخته / gelding |
| Filly | female | ماده / female, age &lt; 5 |
| Mare | female | ماده / female, age ≥ 5 (default if age unknown) |

## Per race

- `males`, `females`, `unknown`, `field_size`
- `mixed_race` flag when both sexes are present  
Stored in `anl_race_sex` / view `anl_v_race_sex`.

## Sex Strength Factor (SSF)

Estimated **only** from historical mixed races:

```
SSF = mean(finish_quality_males) − mean(finish_quality_females)
```

in mixed fields. **Never hardcoded.** Neutral (0) when mixed history is
insufficient. Persisted on the analytics build run + race meta.

## Sex Adjusted Performance Rating

For a female facing males:

```
credit = SSF × (males / field_size)
adjusted_quality = raw_quality + credit
SexAdjustedPR = raw_PR + (mean_adjusted_quality − mean_raw_quality)
```

Males are not boosted for racing females. Mares keep credit for male-field
difficulty.

## Per-horse metrics (`anl_sex_metrics`)

- Male-only / Female-only / Mixed-race performance
- Performance / avg finish / win rate / podium rate vs males and vs females
- Sex Adjusted PR + raw PR + SSF applied

## Reports (boards)

| Board | Score |
|-------|-------|
| Best Mare | Sex Adjusted PR (Mare/Filly) |
| Best Stallion | Sex Adjusted PR (Stallion/Colt) |
| Best Mixed-Race Performer | mixed_race_performance |
| Best Female Against Males | performance_vs_males |
| Most Dominant Male | Sex Adjusted PR (males) |

Season Best also ranks by Sex Adjusted PR (`builder_version` ≥ 2.1.0).

## CLI

```bash
python main.py analytics build --course gonbad-kavous --min-starts 5
python main.py analytics query -q best_mare -n 10
python main.py analytics query -q best_stallion
python main.py analytics query -q best_mixed_race_performer
python main.py analytics query -q best_female_against_males
python main.py analytics query -q most_dominant_male
python main.py std ask -q "best mare"
```
