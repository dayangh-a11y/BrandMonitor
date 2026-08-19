# Prediction Market Metric Definitions

Every score is computed from warehouse rows
(`wh_prediction_entries`, `wh_prediction_statistics`, `wh_prediction_rewards`,
`wh_prediction_winners`, linked `wh_race_results` where available).
No hardcoded horse names, odds, or probabilities.

Notation for a race with runners \(i = 1..n\):

- \(o_i\): decimal win odds (discovered win-style market, typically `pishbar`)
- \(c_i\): survey vote count for cloth \(i\)
- \(p_i\): crowd win probability
- \(r^{m}_i\): crowd (market) rank (1 = favorite)
- \(r^{a}_i\): actual finish rank
- Favorite \(f = \arg\min_i r^{m}_i\)

## Probability construction

1. If survey counts exist: \(p_i = c_i / \sum_j c_j\)
2. Else from odds (vig-removed): \(p_i = (1/o_i) / \sum_j (1/o_j)\)

Source is recorded in `distribution_json.source` ∈ {`survey`,`win_odds`,`none`}.

## Race metrics

| Metric | Formula |
|--------|---------|
| Crowd Favorite | horse with \(r^{m}=1\) |
| Crowd Rank \(r^{m}_i\) | rank of \(p_i\) descending |
| Crowd Win Probability | \(100 \cdot p_f\) |
| Crowd Confidence | \(100 \cdot \big(1 - H(p)/\log_2 n\big)\) where \(H=-\sum p_i\log_2 p_i\) |
| Prediction Distribution | map cloth→\(p_i\) |
| Surprise Index | mean over finishers of \(\|r^{m}_i-r^{a}_i\|/(n-1)\cdot 100\) |
| Upset Score | \((r^{m}_{\text{winner}}-1)/(n-1)\cdot 100\) |
| Favorite Failure Score | \((r^{a}_f-1)/(n-1)\cdot 100\) |
| Prediction Difficulty | \(100 \cdot H(p)/\log_2 n\) |
| Crowd Accuracy | Spearman \(\rho\) of \((r^{m}, r^{a})\) mapped to \(0..100\): \((\rho+1)\cdot 50\) |
| Crowd Bias | \(\mathrm{mean}_i(p_i - \mathbf{1}_{r^{a}_i=1})\) |
| Shock Score | mean(FavoriteFailure, Upset, \(100-\)CrowdAccuracy) |
| Difficulty Score | = Prediction Difficulty |
| Prediction Accuracy | = Crowd Accuracy |
| Participants | \(\sum c_i\) (survey) when available |
| Winners Count | distinct `(pool_type, cloth)` with `place=1` |
| Total Prize Pool | \(\sum\) `total_prize` of pools linked to event |
| Average Prize | mean pool `total_prize` |
| Winning Prediction % | \(100\cdot p_{\text{winner}}\) |

## ML features (per race)

Stored in `anl_prediction_race_metrics.features_json` and columns:

| Feature | Definition |
|---------|------------|
| `crowd_confidence` | confidence in \(0..1\) |
| `crowd_probability` | \(p_f\) |
| `prediction_gap` | \(1 - r^{a}_f\) (negative ⇒ favorite underperformed) |
| `surprise_index` | race Surprise Index / 100 scale kept as computed |
| `public_bias` | Crowd Bias |
| `favorite_rank` | \(r^{m}_f\) (=1) |
| `favorite_failed` | \(1\) if \(r^{a}_f \neq 1\) else \(0\) |
| `upset_score` | Upset Score |
| `prediction_entropy` | \(H(p)\) |
| `prediction_variance` | population stdev of \(\{p_i\}\) |

## Entity metrics (horse / trainer / jockey / owner / sire)

For each start of entity \(e\), define residual gap \(g = r^{m} - r^{a}\)
(positive ⇒ finished better than public expected).

| Metric | Formula |
|--------|---------|
| Public Popularity Score | \(100\cdot\mathrm{mean}(p)\) over starts |
| Public Trust Score | win rate when entity was crowd favorite |
| Overrated Score | \(\mathrm{mean}(\|g\|)\) over starts with \(g<0\) |
| Underrated Score | \(\mathrm{mean}(g)\) over starts with \(g>0\) |
| Unpredictability Score | \(\mathrm{pstdev}(\|r^{m}-r^{a}\|)\) |
| Surprise Frequency | % starts with \(\|r^{m}-r^{a}\| \ge 2\) |
| Favorite Failure Frequency | % of favorite starts with \(r^{a}\neq 1\) |
| Upset Victory Frequency | % of wins where \(r^{m}\ge 3\) |
| Average Prediction Rank | \(\mathrm{mean}(r^{m})\) |
| Average Actual Rank | \(\mathrm{mean}(r^{a})\) |
| Prediction Gap | \(\mathrm{mean}(g)\) |

Trainer / owner / sire rows use the same formulas on starts joined through
`wh_race_results` when `wh_prediction_events.wh_race_id` and horse ids link.

## Reproducibility

```bash
python main.py prediction build
```

Rebuild deletes and recomputes `anl_prediction_*` from `wh_prediction_*`,
which themselves rebuild from the latest `raw_prediction_snapshots` per key.
