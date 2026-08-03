# SCORE_METHOD.md — postal_score_v1 Method Specification

**Algorithm:** `postal_score_v1`  
**Status:** Implemented and reproducible; **not yet scientifically defensible** as a calibrated industry index.  
**This document freezes the method as currently shipped.** Score values were **not** changed by the audit.

**Code:** `postal/dimensions.py`, `postal/scoring.py`, `postal/weights.py`  
**Config:** `config/scoring_weights.yaml`  
**Official inputs:** `config/official_companies.yaml` (`data_quality: curated_v1`)  
**Machine-readable explainer:** `SCORE_EXPLAINER.json`

---

## 1. Top-level formula

\[
\text{CompanyScore} = \mathrm{round}\Big(\sum_{i=1}^{8} w_i \cdot D_i,\ 2\Big),\quad D_i \in [0,100],\ \sum w_i = 1
\]

No hidden terms. No ML model. No time decay at company level. Clamping to \([0,100]\) is the only post-processing.

**Reproducibility check:** recomputing from stored inputs must match the published score within \(0.01\). Verified for all six companies in `SCORE_EXPLAINER.json` (`reproducible: true`).

---

## 2. Component catalog

For each component: data source, formula, weight, required fields, confidence, missing data, assumptions, bias.

Confidence below is an **audit estimate** of evidence quality. It is **not** multiplied into the published score.

---

### 2.1 Customer Satisfaction — weight **0.22**

| Field | Value |
|-------|-------|
| **Data source** | `pi_reviews` (ingested Google Maps / demo warehouses) + rule NLP sentiment (`collectors/phase11/nlp.py`) |
| **Formula** | \(CSI = 100\cdot\frac{pos + 0.5\cdot neu}{n}\); \(R = 100\cdot\frac{\overline{rating}}{5}\); \(D = 0.60\cdot CSI + 0.40\cdot R\). If \(n=0\): \(D=50\) (prior). |
| **Weight** | `0.22` |
| **Required input fields** | `sentiments{Positive,Neutral,Negative}`, `avg_rating`, `review_count` / `n` |
| **Confidence level** | High only when \(n\gtrsim 100\); else moderate/low. NLP adds uncertainty (~×0.95). See per-company `SCORE_EXPLAINER.json`. |
| **Missing data** | Human-validated sentiment labels; verified review authenticity; non-Maps channels; demographic representativeness |
| **Assumptions** | Star ratings and NLP sentiment jointly proxy “satisfaction”; Neutral counts as half-positive; Maps reviews represent customers |
| **Possible bias** | Selection bias (angry customers over-review); Tipax overweighted by sample size; NLP keyword false positives/negatives; English/Persian imbalance |

---

### 2.2 Delivery Speed — weight **0.14**

| Field | Value |
|-------|-------|
| **Data source** | `official_delivery_times.intercity_typical_days` in curated official YAML → `pi_official_profiles` |
| **Formula** | Linear inverse map: `excellent_days=1 → 100`, `poor_days=7 → 0`: \(D = 100\cdot\big(1 - \frac{days-1}{7-1}\big)\) clamped to \([0,100]\). Default days if missing: **3** (code fallback). |
| **Weight** | `0.14` |
| **Required input fields** | `intercity_typical_days`; benchmarks `excellent_days`, `poor_days` |
| **Confidence level** | **Low (~0.45)** — curated estimate, not measured SLA |
| **Missing data** | Actual scanned transit times; city-pair matrices; on-time %; remote vs metro split beyond a single scalar |
| **Assumptions** | One intercity “typical days” number represents national speed; linear utility between 1 and 7 days |
| **Possible bias** | Favors urban/express brands; AloPeyk same-city speed mapped through intercity field is category-mismatched; National Post penalized for economy product mix |

---

### 2.3 Service Coverage — weight **0.12**

| Field | Value |
|-------|-------|
| **Data source** | Official `cities_covered_official`, `provinces_covered_official`, `branch_count_official` + observed `COUNT(pi_branches)` |
| **Formula** | \(S_c=100\min(cities,200)/200\), \(S_p=100\min(prov,31)/31\), \(S_b=100\min(\max(off,obs),400)/400\); \(D=0.40 S_c + 0.25 S_p + 0.35 S_b\) |
| **Weight** | `0.12` |
| **Required input fields** | cities, provinces, branches_official, branches_observed; targets in config |
| **Confidence level** | Moderate if observed branches exist; lower if only curated official counts |
| **Missing data** | Verified city list; serviceable vs presence; capacity per branch |
| **Assumptions** | Hitting targets = “full” coverage; max(official,observed) is fair; Post’s huge network is capped at targets (soft-cap by design) |
| **Possible bias** | Cap at 200/400 compresses Post vs Tipax; under-observed brands look weaker on branch_eff if official counts are optimistic |

---

### 2.4 Pricing — weight **0.10**

| Field | Value |
|-------|-------|
| **Data source** | Curated `official_pricing.price_index` (relative scalar; also stores illustrative تومان base rates) |
| **Formula** | Inverse linear: `best_index=0.70 → 100`, `worst_index=1.40 → 0` |
| **Weight** | `0.10` |
| **Required input fields** | `price_index`; optional base/extra kg (not used in formula today) |
| **Confidence level** | **Low (~0.40)** |
| **Missing data** | Live tariff tables; remote surcharges; B2B discounts; weight/zone matrices |
| **Assumptions** | Lower index = better for customers; single scalar comparable across business models |
| **Possible bias** | Dynamic marketplace pricing (AloPeyk) poorly represented; “cheaper” ≠ better value |

---

### 2.5 Service Variety — weight **0.08**

| Field | Value |
|-------|-------|
| **Data source** | Curated `services[]` list vs fixed 12-item catalog in code |
| **Formula** | \(D = 100 \cdot \|services \cap catalog\| / 12\) |
| **Weight** | `0.08` |
| **Required input fields** | `services` (list of string codes) |
| **Confidence level** | Moderate-low (~0.60) |
| **Missing data** | Verified product catalog; depth/quality of each service |
| **Assumptions** | Each catalog item equal value; presence beats absence regardless of quality |
| **Possible bias** | Catalog includes `urban_ondemand` and `registered_mail` — postal vs marketplace apples-to-oranges; rewards checklist stuffing |

**Catalog (fixed in code):**  
`domestic_express`, `domestic_economy`, `door_to_door`, `branch_to_branch`, `international`, `insurance`, `cod`, `tracking`, `packaging`, `pickup`, `registered_mail`, `urban_ondemand`

---

### 2.6 Transparency — weight **0.10**

| Field | Value |
|-------|-------|
| **Data source** | Official profile fields: tracking, insurance, pricing, working_hours, customer_support, cod |
| **Formula** | Six binary checks; \(D = 100 \cdot (\#yes)/6\) |
| **Weight** | `0.10` |
| **Required input fields** | `tracking.available`; insurance available/notes; pricing base or index; non-empty working_hours; support.phone; `"available" in cod` |
| **Confidence level** | Low discriminative power (~0.40–0.50) when all companies score 100 |
| **Missing data** | Independent verification that published info is accurate/up-to-date |
| **Assumptions** | Disclosure presence ≡ transparency; COD `available: false` still counts as disclosed |
| **Possible bias** | **Saturation bias** — current curated set all score 100; adds a constant +10 points to every company |

---

### 2.7 Complaint Rate — weight **0.12**

| Field | Value |
|-------|-------|
| **Data source** | Negative-review NLP `complaint_category` counts + sentiment mix from `pi_reviews` |
| **Formula** | \(rate = complaint\_events/n\); \(neg = Neg/n\); \(D = 0.70(100-60\cdot rate) + 0.30(100(1-neg))\). If \(n=0\): \(D=50\). |
| **Weight** | `0.12` |
| **Required input fields** | `sentiments`, `complaints` (per category counts for Negative reviews) |
| **Confidence level** | Scales with \(n\); reduced when `other` dominates taxonomy |
| **Missing data** | Official complaint tickets; resolution rate; severity; verified categories |
| **Assumptions** | One complaint category per negative review; higher score = fewer complaints; rate and neg_share are complementary |
| **Possible bias** | Double-counting negativity (rate ≈ neg_share when one category/review); `other` dump weakens interpretability; volume brands look worse if complainers concentrate |

---

### 2.8 Branch Quality — weight **0.12**

| Field | Value |
|-------|-------|
| **Data source** | Mean of `pi_branch_intelligence.branch_score` (else fallback \(100\cdot\overline{google\_rating}/5\), else prior 50) |
| **Formula** | \(D = \mathrm{mean}(branch\_score_j)\) |
| **Weight** | `0.12` |
| **Required input fields** | list of branch scores; or avg google rating + branch count |
| **Confidence level** | Depends on branch count and per-branch review volume (branch scores shrink to prior) |
| **Missing data** | Mystery-shop / ops QA; equalized sampling per branch |
| **Assumptions** | Unweighted mean of branches is fair; branch score formula is appropriate |
| **Possible bias** | Many low-review branches pull mean to ~50 via prior shrinkage; unequal review depth across network |

#### Branch score sub-formula (feeds Branch Quality)

\[
\kappa = \frac{n}{n+N_{full}},\ N_{full}=20,\ prior=50
\]
\[
raw = 0.35 R + 0.30 S + 0.20 C + 0.15 V
\]
\[
score = \kappa\cdot raw + (1-\kappa)\cdot prior
\]

Where \(R=100\cdot rating/5\), \(S=CSI\), \(C=100-55\cdot rate\), \(V=100\cdot\kappa\).

---

## 3. Weights table (must sum to 1.0)

See also `WEIGHTS_TABLE.csv`.

| Component | Weight | Role |
|-----------|-------:|------|
| customer_satisfaction | 0.22 | Experience evidence |
| delivery_speed | 0.14 | Official speed claim |
| service_coverage | 0.12 | Network footprint |
| complaint_rate | 0.12 | Experience risk |
| branch_quality | 0.12 | Local execution |
| pricing | 0.10 | Cost signal |
| transparency | 0.10 | Disclosure checklist |
| service_variety | 0.08 | Product breadth |
| **Sum** | **1.00** | |

Weights are **judgmental**, not regression-fitted to outcomes (retention, NPS survey, claim rates, etc.).

---

## 4. What the method does *not* do

- Does not use LLM black-box scores
- Does not change weights by company
- Does not impute missing official fields from competitors (except numeric defaults: delivery days→3, price_index→1.0)
- Does not adjust published scores by confidence (confidence is audit-only)

---

## 5. How to reproduce a score

```bash
python3 scripts/build_postal_intelligence.py   # rebuild DB (deterministic given inputs)
# Or recompute one company via postal.scoring.compute_company_score(...)
```

Given the same `official` dict + `review_stats` + `branch_stats` + `config/scoring_weights.yaml`, `compute_company_score` must return the same rounded total.

---

## 6. Scientific defensibility gate (audit conclusion)

`postal_score_v1` is **explainable and reproducible** but **not yet scientifically defensible** until at least:

1. Official speed/price/coverage replaced or validated with measured or primary-source tariffs  
2. Weights calibrated or stress-tested against external outcomes  
3. Transparency metric redesigned (currently non-discriminative)  
4. NLP complaint taxonomy validated; reduce `other` mass  
5. Confidence / missing-data rules optionally folded into a *separate* reported interval (without silently shifting point scores unless product decides so)
