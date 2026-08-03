# SCORE_AUDIT.md — postal_score_v1 Audit Report

**Audit date:** 2026-08-03  
**Algorithm:** `postal_score_v1`  
**Score values changed:** **No** (explicit requirement)  
**Companion artifacts:** `SCORE_METHOD.md`, `WEIGHTS_TABLE.csv`, `SCORE_EXPLAINER.json`

---

## 0. Executive verdict

| Criterion | Result |
|-----------|--------|
| Explainable | **Yes** — each dimension stores formula, inputs, explanation |
| Reproducible | **Yes** — all 6 companies recompute to the published score |
| Scientifically defensible | **Not yet** — curated official inputs, judgmental weights, saturated transparency, NLP/Maps biases |
| Hidden heuristics / black box | **None in the arithmetic**; several **documented judgmental** choices (weights, benchmarks, priors, catalog) |

**Overall confidence (audit-only, does not change scores):**

| Rank | Company | Score | Overall confidence | Band |
|-----:|---------|------:|-------------------:|------|
| 1 | Tipax | 69.68 | 0.649 | moderate |
| 2 | Chapar | 69.34 | 0.594 | moderate |
| 3 | Mahex | 65.86 | 0.535 | low |
| 4 | Post | 62.91 | 0.531 | low |
| 5 | Pishro | 60.15 | 0.230 | very_low |
| 6 | AloPeyk | 59.40 | 0.528 | low |

Confidence model: per-dimension evidence quality ∈ [0,1], then \(\sum w_i conf_i\); ×0.7 if zero reviews. Details in `SCORE_EXPLAINER.json`.

---

## 1. Component audit summary

| Component | Weight | Typical confidence | Critical issue |
|-----------|-------:|--------------------|----------------|
| customer_satisfaction | 0.22 | rises with \(n\) | Maps selection bias + rule NLP |
| delivery_speed | 0.14 | ~0.45 | Curated SLA, not measured |
| service_coverage | 0.12 | ~0.55 | Curated counts; target caps |
| pricing | 0.10 | ~0.40 | Relative `price_index` not live tariffs |
| service_variety | 0.08 | ~0.60 | Equal checklist items |
| transparency | 0.10 | ~0.40 | **All companies = 100** (non-discriminative) |
| complaint_rate | 0.12 | rises with \(n\) | Correlated with satisfaction; `other` mass |
| branch_quality | 0.12 | rises with branches | Prior shrinkage → means near 50 |

Full field-by-field method: `SCORE_METHOD.md`. Spreadsheet form: `WEIGHTS_TABLE.csv`.

---

## 2. Cross-cutting findings (do not change scores)

1. **Transparency saturation:** every company contributes exactly **+10.00** points (`100 × 0.10`). Ranking is unaffected by this term today; it inflates absolute levels.
2. **Official-data dependence:** delivery, pricing, coverage, variety, transparency are dominated by `curated_v1` YAML. Missing independently verified tariffs/SLAs → confidence drop of roughly **0.35–0.55** on those dimensions.
3. **Pishro zero-evidence failure mode:** \(n=0\) reviews and \(0\) branches → satisfaction/complaint/branch_quality all **prior 50**. Score **60.15** is mostly official checklist arithmetic — **very_low** confidence (0.23).
4. **Complaint ↔ satisfaction coupling:** both use the same sentiment stream; Tipax’s high volume of negatives depresses both dimensions (not independent factors).
5. **Category mismatch:** AloPeyk (on-demand urban) scored with postal intercity speed & branch-coverage targets — structural bias against marketplace model on coverage/pricing.
6. **Weights are not calibrated** to external outcomes (claims, delivery scans, survey NPS).

---

## 3. Per-company score explanation

Contribution identity (verified):  
\(\text{score} \approx \sum_i w_i D_i\) (rounding to 2 decimals).

### 3.1 Tipax — **69.68** (rank 1) — confidence 0.649

| Dimension | \(D\) | \(w\) | Contribution |
|-----------|------:|------:|-------------:|
| service_coverage | 100.00 | 0.12 | 12.00 |
| delivery_speed | 83.33 | 0.14 | 11.67 |
| customer_satisfaction | 49.19 | 0.22 | 10.82 |
| transparency | 100.00 | 0.10 | 10.00 |
| complaint_rate | 62.34 | 0.12 | 7.48 |
| service_variety | 83.33 | 0.08 | 6.67 |
| branch_quality | 50.34 | 0.12 | 6.04 |
| pricing | 50.00 | 0.10 | 5.00 |
| **Total** | | | **69.68** |

**Why this score**

- Wins primarily on **coverage (100)** and **claimed intercity speed (2 days → 83.33)** plus full transparency (+10).
- Customer evidence is large (\(n=1866\)) but mixed: CSI≈45.9, avg rating≈2.71 → satisfaction only **49.19**.
- Complaint rate **62.34** (higher=better) still mid because ~52% negatives; many NLP labels fall in `other` (695) — taxonomy confidence reduced.
- Branch quality ~**50.3** across 373 branches (prior shrinkage / middling ratings).
- Pricing mid (**50**) at price_index 1.05.

**Missing data / confidence hit**

- Unverified official SLA & tariffs (delivery/pricing confidence ~0.4–0.45).
- NLP `other` share high → complaint confidence −0.10.
- Despite large \(n\), Maps bias remains → satisfaction confidence capped ~0.85×0.95.

---

### 3.2 Chapar — **69.34** (rank 2) — confidence 0.594

| Dimension | \(D\) | Contribution |
|-----------|------:|-------------:|
| delivery_speed | 83.33 | 11.67 |
| transparency | 100.00 | 10.00 |
| service_coverage | 93.00 | 11.16 |
| customer_satisfaction | 49.92 | 10.98 |
| complaint_rate | 64.59 | 7.75 |
| service_variety | 75.00 | 6.00 |
| pricing | 57.14 | 5.71 |
| branch_quality | 50.53 | 6.06 |
| **Total** | | **69.34** |

**Why this score**

- Nearly ties Tipax: same speed claim (2 days), strong coverage (cities 200 / branches official 320 / observed 19 → **93**), slightly better pricing index (1.00 → **57.14**).
- Satisfaction **49.92** on only **122** reviews (similar mix to Tipax) — sample much thinner → lower confidence than Tipax.
- Variety 9/12 catalog → **75** (vs Tipax 10/12).

**Missing data / confidence hit**

- Small \(n\) vs Tipax; observed branches only 19 vs official 320 (coverage cross-check weak).
- Same curated SLA/tariff limitations.

---

### 3.3 Mahex — **65.86** (rank 3) — confidence 0.535

| Dimension | \(D\) | Contribution |
|-----------|------:|-------------:|
| delivery_speed | 83.33 | 11.67 |
| transparency | 100.00 | 10.00 |
| customer_satisfaction | 58.33 | 12.83 |
| complaint_rate | 67.60 | 8.11 |
| service_coverage | 62.33 | 7.48 |
| service_variety | 66.67 | 5.33 |
| branch_quality | 51.27 | 6.15 |
| pricing | 42.86 | 4.29 |
| **Total** | | **65.86** |

**Why this score**

- Best-in-set **customer_satisfaction (58.33)** among mid-pack: \(n=60\), more positives than negatives, avg rating ≈3.17.
- Coverage weaker (120 cities / 180 official branches / 17 observed → **62.33**) pulls total down vs Tipax/Chapar.
- Price_index 1.10 → pricing **42.86** (penalty).
- Speed claim still 2 days → same 83.33 as Tipax (curated; not independently proven).

**Missing data / confidence hit**

- \(n=60\) → satisfaction/complaint confidence moderate-low.
- Official footprint not well corroborated by observed branches.

---

### 3.4 Post — **62.91** (rank 4) — confidence 0.531

| Dimension | \(D\) | Contribution |
|-----------|------:|-------------:|
| service_coverage | 100.00 | 12.00 |
| transparency | 100.00 | 10.00 |
| pricing | 78.57 | 7.86 |
| delivery_speed | 50.00 | 7.00 |
| service_variety | 75.00 | 6.00 |
| complaint_rate | 52.87 | 6.34 |
| branch_quality | 48.31 | 5.80 |
| customer_satisfaction | 35.96 | 7.91 |
| **Total** | | **62.91** |

**Why this score**

- Strongest **pricing (78.57)** and capped **coverage 100**, but weakest **satisfaction (35.96)** among companies with reviews (\(n=55\), avg≈2.11, mostly negative).
- Intercity typical days **4** → speed only **50**.
- Thin observed branch sample (8) for a national network — Maps ingest incompleteness, not true network size.

**Missing data / confidence hit**

- Review sample tiny vs real Post footprint → high extrapolation risk.
- Coverage uses curated official 9000 branches / 1200 cities but observed only 8 → official side dominates; confidence limited.

---

### 3.5 Pishro — **60.15** (rank 5) — confidence **0.230 (very_low)**

| Dimension | \(D\) | Contribution | Evidence |
|-----------|------:|-------------:|----------|
| transparency | 100.00 | 10.00 | curated disclosure |
| delivery_speed | 66.67 | 9.33 | curated 3-day typical |
| pricing | 64.29 | 6.43 | curated index 0.95 |
| service_variety | 66.67 | 5.33 | curated services |
| service_coverage | 50.41 | 6.05 | curated 90/25/140 |
| customer_satisfaction | **50.00** | 11.00 | **PRIOR — no reviews** |
| complaint_rate | **50.00** | 6.00 | **PRIOR — no reviews** |
| branch_quality | **50.00** | 6.00 | **PRIOR — no branches** |
| **Total** | | **60.15** | |

**Why this score**

- **No reviews and no observed branches** in the intelligence DB.
- Score is almost entirely official curated fields + priors.
- Must **not** be treated as empirically comparable to Tipax.

**Missing data (severe)**

- `reviews`, `branch_intelligence`, verified tariffs/SLA.
- Confidence reduced to **0.23**; estimated confidence decrease vs a well-evidenced peer (**Tipax 0.65**): about **−0.42 absolute** (~65% relative drop).

---

### 3.6 AloPeyk — **59.40** (rank 6) — confidence 0.528

| Dimension | \(D\) | Contribution |
|-----------|------:|-------------:|
| delivery_speed | 83.33 | 11.67 |
| transparency | 100.00 | 10.00 |
| customer_satisfaction | 67.86 | 14.93 |
| complaint_rate | 78.23 | 9.39 |
| branch_quality | 52.82 | 6.34 |
| service_variety | 41.67 | 3.33 |
| pricing | 21.43 | 2.14 |
| service_coverage | 13.38 | 1.61 |
| **Total** | | **59.40** |

**Why this score**

- Best **satisfaction (67.86)** and **complaint_rate (78.23)** on \(n=43\) (more positive mix, avg≈3.51).
- Crushed by **coverage 13.38** (20 cities / 10 provinces / 15 official branches) and **pricing 21.43** (price_index 1.25) — postal network metrics applied to an on-demand courier.
- Speed uses intercity field (mapped from same-city product) → **83.33** may overstate “postal” comparability.

**Missing data / confidence hit**

- Small \(n\); category-inappropriate coverage/price constructs; dynamic pricing not captured.

---

## 4. Reproducibility protocol

For each company in `SCORE_EXPLAINER.json`:

1. Load official profile from `config/official_companies.yaml`.
2. Aggregate `pi_reviews` sentiments/complaints/avg rating.
3. Aggregate branch intelligence scores / observed counts.
4. Call `postal.scoring.compute_company_score`.
5. Assert `abs(recomputed - published) < 0.011`.

**Result:** `meta.all_companies_reproducible = true`.

---

## 5. Missing-data → confidence impact (rule of thumb used in audit)

| Situation | Approx. confidence effect |
|-----------|---------------------------|
| Dimension uses only curated official field | conf ≈ 0.40–0.55 |
| Reviews \(n=0\) (prior) | conf ≈ 0.20 on that dimension; overall ×0.7 |
| Reviews \(n<30\) | conf ≈ 0.55 on review dims |
| Reviews \(n\ge100\) | conf ≈ 0.85–0.90 before NLP factor |
| Transparency all-yes saturation | −0.10 on transparency conf |
| Complaint `other` share >50% | −0.10 on complaint conf |
| No observed branches to check coverage | −0.15 on coverage conf |

These rules are **documented audit heuristics**. They do **not** alter `postal_score_v1` outputs.

---

## 6. Recommendations (for a future version — not applied now)

1. Split **PostalScore** vs **EvidenceGrade**/confidence band in the UI.  
2. Replace curated speed/price with primary-source tariffs or mark as `estimate`.  
3. Redesign transparency (accuracy, freshness, completeness) to restore discrimination.  
4. Calibrate weights or publish sensitivity analysis.  
5. Down-rank or flag companies with \(n=0\) (Pishro) as **insufficient evidence**.  
6. Validate NLP categories; reduce `other`.  
7. Score AloPeyk in an **urban courier** peer group, not classic postal coverage.

---

## 7. Artifact index

| File | Purpose |
|------|---------|
| `SCORE_METHOD.md` | Normative method: sources, formulas, assumptions, bias |
| `SCORE_AUDIT.md` | This audit + per-company why |
| `WEIGHTS_TABLE.csv` | Machine-readable weights + audit columns |
| `SCORE_EXPLAINER.json` | Full reproducible breakdown + confidence per company/dimension |
