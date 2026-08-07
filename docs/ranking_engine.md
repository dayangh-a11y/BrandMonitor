# Ranking Engine Redesign (v2)

The previous Season Best board was statistically invalid when horses had
a single start: win/place/consistency collapsed to 100% and prize money
decided the order.

## Rules

1. **Minimum starts** (default `5`, CLI `--min-starts`) — exclude below threshold.
2. **Separated boards** — never mix concepts:
   - Season Best Horse (`best_season`) — Performance Rating
   - Most Successful (`most_successful`) — wins
   - Highest Earnings (`highest_earnings`)
   - Highest Win Rate (`highest_win_rate`)
   - Best Form (`best_form`)
   - Most Consistent (`most_consistent`)
3. **Earnings never dominate PR** — excluded from Performance Rating (tie-break only).
4. **PR rewards** wins, seconds, thirds, podium rate, consistency, avg finish,
   competition strength (difficulty), form, speed.
5. **If every horse has only one race** → Season Best returns **INSUFFICIENT DATA**.
6. **Sample-size confidence**: 1=very_low … 10+=high.
7. Every board row exposes starts, confidence, qualification status, reasons.

## CLI

```bash
python main.py analytics build --course gonbad-kavous --min-starts 5
python main.py analytics query -q season_best_status
python main.py analytics query -q best_season -n 10
python main.py analytics query -q most_successful
python main.py analytics query -q highest_earnings
python main.py analytics query -q highest_win_rate
python main.py analytics query -q best_form
python main.py analytics query -q most_consistent
```

## Performance Rating weights (earnings off)

| Component | Weight |
|-----------|--------|
| Win rate (wins/starts) | 18 |
| Seconds rate | 8 |
| Thirds rate | 5 |
| Podium rate | 15 |
| Avg finish map | 15 |
| Consistency (≥3 starts full / ≥2 half) | 12 / 6 |
| Difficulty (competition) | 12 |
| Form score 5 | 10 |
| Speed index | 5 |

Sort tie-break after PR: wins → places → avg_finish → form → **earnings last**.
