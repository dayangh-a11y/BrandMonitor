# Market-Specific Analytics Engine

**Never use one ranking model for every betting market.**

Package: `src/markets/` — each market has its own scoring model and returns a
standard answer payload.

## Output rules (every answer)

- Prediction  
- Confidence  
- Reasons  
- Metrics Used  
- Sample Size  
- Data Quality  
- Applicable Market  

## Markets

| Market | Score model | Predicts |
|--------|-------------|----------|
| **Win** | `win_strength` (win_rate heavy) | Winner, Top 3, winning confidence & probability |
| **Place** | `place_strength` (place/consistency) | Top2 / Top3 / Top5 probs, podium confidence |
| **Head-to-Head** | pairwise blend | Complete N×N matrix: ahead probs, gaps, historical/distance/track/trainer/jockey H2H |
| **Without Favorite** | Win model on remaining | Detect favorite → exclude → best / 2nd / 3rd remaining |
| **Value** | model − perception | Value Score, confidence, reasons |
| **Risk** | variance/reliability mix | Risk, reliability, variance, consistency, volatility |
| **Surprise** | perception gaps + trends | Dark / hidden / improved / under / overrated |
| **Matchup** | factor-by-factor A vs B | Finish-ahead probs — **never season ranking** |

## Pairwise / Matchup

```bash
python main.py markets analyze --race-id 123
python main.py markets analyze --race-id 123 -m win
python main.py markets analyze --race-id 123 -m h2h
python main.py markets build --course gonbad-kavous -n 20
python main.py markets matchup -q "دنزی بوی یا لیدی سانگ"
python main.py markets list
```

Matchup compares: recent form, distance, track, competition strength, speed,
trainer, jockey, rest days, weight, age, sex, field strength, opponent strength.

## Persistence

- `anl_market_races` — per-race market JSON snapshots  
- `anl_market_pairwise` — full pairwise matrix rows  
- `anl_market_matchups` — audited A vs B answers  
