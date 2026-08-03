# Scoring Methodology — BrandMonitor Postal Intelligence

**Algorithm version:** `postal_score_v1`  
**Config file:** `config/scoring_weights.yaml`  
**Goal:** Every company and branch score is explainable. No black-box ML.

---

## 1. Company Postal Score (0–100)

$$
\text{CompanyScore} = \sum_i w_i \cdot D_i
$$

Where each dimension \(D_i \in [0,100]\) and weights \(w_i\) sum to **1.0**.

### Default weights

| Dimension | Weight | Primary inputs |
|-----------|-------:|----------------|
| Customer Satisfaction | 0.22 | Review sentiment + average star rating |
| Delivery Speed | 0.14 | Official intercity typical days |
| Service Coverage | 0.12 | Official cities / provinces / branches (+ observed) |
| Pricing | 0.10 | Official price index (lower → better) |
| Service Variety | 0.08 | Count of offered services vs catalog |
| Transparency | 0.10 | Checklist: tracking, insurance, prices, hours, support, COD policy |
| Complaint Rate | 0.12 | Complaint events & negative share (higher score = fewer complaints) |
| Branch Quality | 0.12 | Mean branch intelligence scores |

Weights are **fully configurable**. Changing YAML and rebuilding recalculates all scores.

Stored per company in `pi_company_scores` with:
- `dimensions_json` — each dimension score + inputs + formula + explanation
- `weights_json` — weights used
- `explanation_json.why` — line-by-line contribution narrative
- `explanation_json.weighted_contribution` — \(w_i \times D_i\)

---

## 2. Dimension formulas

### 2.1 Customer Satisfaction

\[
CSI = 100 \times \frac{pos + 0.5 \cdot neu}{n}
\]
\[
rating\_score = 100 \times \frac{avg\_rating}{5}
\]
\[
D = 0.60 \cdot CSI + 0.40 \cdot rating\_score
\]

If \(n=0\): prior **50**.

### 2.2 Delivery Speed (official data)

Linear map of `official_delivery_times.intercity_typical_days`:

- `excellent_days` (default 1) → 100  
- `poor_days` (default 7) → 0  

### 2.3 Service Coverage

\[
D = 0.40\cdot S_{cities} + 0.25\cdot S_{provinces} + 0.35\cdot S_{branches}
\]

Each \(S\) is \(100 \times \min(value, target)/target\).  
Branch count uses \(\max(official, observed)\).

### 2.4 Pricing

Linear inverse map of official `price_index`:

- `best_index` (0.70) → 100  
- `worst_index` (1.40) → 0  

### 2.5 Service Variety

\[
D = 100 \times \frac{|services \cap catalog|}{|catalog|}
\]

Catalog includes express, economy, door-to-door, international, insurance, COD, tracking, packaging, pickup, etc.

### 2.6 Transparency

Six binary checks (tracking available, insurance disclosed, pricing published, hours published, support phone, COD policy disclosed):

\[
D = 100 \times \frac{\#yes}{6}
\]

### 2.7 Complaint Rate

\[
rate = \frac{complaint\_events}{n},\quad
neg\_share = \frac{neg}{n}
\]
\[
D = 0.70\cdot(100 - 60\cdot rate) + 0.30\cdot(100\cdot(1-neg\_share))
\]

Higher is better (fewer complaints).

### 2.8 Branch Quality

Mean of `pi_branch_intelligence.branch_score` for the company.  
Fallback: \(100 \times avg\_google\_rating / 5\).

---

## 3. Branch Score (0–100)

Configurable `branch_weights`:

\[
raw = w_r R + w_s S + w_c C + w_v V
\]
\[
\kappa = \frac{n}{n + N_{full}},\quad
score = \kappa\cdot raw + (1-\kappa)\cdot prior
\]

| Symbol | Meaning |
|--------|---------|
| \(R\) | \(100 \times avg\_rating/5\) |
| \(S\) | CSI-style sentiment score |
| \(C\) | \(100 - 55 \times complaint\_rate\) |
| \(V\) | \(100 \times \kappa\) (volume confidence) |
| \(N_{full}\) | `min_reviews_for_full_confidence` (default 20) |
| \(prior\) | default 50 |

Branch intelligence also stores: overall rating, review count, complaint categories, sentiment mix, monthly review trend, last activity, and the full explanation object.

---

## 4. Geo rankings (province / city)

For each geography × company, aggregate local reviews and apply the **same branch-score formula**. Companies are ranked by that local score (ties broken by review count).

---

## 5. Worked example (illustrative)

Suppose Tipax dimensions:

| Dimension | Score | Weight | Contribution |
|-----------|------:|-------:|-------------:|
| customer_satisfaction | 48 | 0.22 | 10.56 |
| delivery_speed | 83 | 0.14 | 11.62 |
| service_coverage | 90 | 0.12 | 10.80 |
| pricing | 50 | 0.10 | 5.00 |
| service_variety | 83 | 0.08 | 6.64 |
| transparency | 100 | 0.10 | 10.00 |
| complaint_rate | 55 | 0.12 | 6.60 |
| branch_quality | 52 | 0.12 | 6.24 |
| **Total** | | **1.00** | **≈67.5** |

Exact live numbers are in `output/postal_intelligence/company_scores.json` after rebuild.

---

## 6. What is *not* in the score

- Undocumented scrape heuristics with hidden weights
- Opaque LLM “vibes” scores without stored explanations
- Single-metric rating-only rankings (legacy `score_v1` still exists under `scoring/` for review-analysis demos, but Postal Intelligence uses `postal_score_v1`)

---

## 7. Rebuild

```bash
python scripts/build_postal_intelligence.py
```

Outputs: `data/postal_intelligence.db`, `output/postal_intelligence/**`.
