# Postal Intelligence Platform

BrandMonitor Phase 2 evolves from “review collection” into a **comparison & intelligence platform for Iranian postal companies**.

This phase intentionally **does not add new review sources**. It consumes existing warehouses (Tipax Iran, Phase 11 multi-brand, demo) plus a curated **official company dataset**.

---

## Capabilities

1. **Scoring Engine (0–100)** — weighted, configurable, explainable dimensions  
2. **Official Company Dataset** — services, pricing, coverage, COD, insurance, tracking, limits… stored apart from reviews  
3. **Branch Intelligence** — rating, volume, complaints, sentiment, trend, last activity, branch score  
4. **Company Comparison** — auto tables for prices, services, coverage, delivery time, ratings, complaints, branches  
5. **Province & City Rankings** — local competitive standings  
6. **Dashboards** — ranking, complaints, sentiment, trends, interactive map  
7. **Documentation** — `docs/SCORING_METHODOLOGY.md`

---

## Architecture

```text
config/official_companies.yaml ──► pi_official_profiles
config/scoring_weights.yaml  ──► postal scoring engine
data/tipax_iran.db           ─┐
data/phase11_multisource.db  ─┼─► ingest + NLP ─► pi_branches / pi_reviews
data/analytics_demo.db       ─┘
                                    │
                                    ▼
                    branch intelligence + company scores
                    comparison + geo rankings
                                    │
                                    ▼
              data/postal_intelligence.db
              output/postal_intelligence/{csv,json,dashboards}
              GET /postal/* API
```

### Schema (new tables)

| Table | Purpose |
|-------|---------|
| `pi_companies` | Canonical company registry |
| `pi_official_profiles` | Structured official data (JSON columns) |
| `pi_branches` | Observed branches (geo + Maps metadata) |
| `pi_reviews` | Reviews + rule NLP labels |
| `pi_company_scores` | Explainable postal scores |
| `pi_branch_intelligence` | Per-branch intelligence card |
| `pi_geo_rankings` | Province/city rankings |
| `pi_comparisons` | Snapshot comparison payload |
| `pi_meta` | Build metadata |

Official data is **never mixed into review rows**.

---

## Build

```bash
pip install -r requirements.txt
python scripts/build_postal_intelligence.py
```

Artifacts:

- `data/postal_intelligence.db`
- `output/postal_intelligence/company_scores.json`
- `output/postal_intelligence/official_company_dataset.json`
- `output/postal_intelligence/company_comparison.json`
- `output/postal_intelligence/branch_ranking.csv`
- `output/postal_intelligence/province_rankings.csv`
- `output/postal_intelligence/dashboards/*.html`

Open dashboards:

```bash
python -m http.server 8765 --directory output/postal_intelligence/dashboards
```

---

## API

Requires existing `API_TOKEN`. Set `POSTAL_DB_PATH` if needed (default `data/postal_intelligence.db`).

| Method | Path | Description |
|--------|------|-------------|
| GET | `/postal/companies` | Companies + latest scores |
| GET | `/postal/companies/{slug}/score` | Full explainable score |
| GET | `/postal/official/{slug}` | Official profile |
| GET | `/postal/branches` | Branch intelligence |
| GET | `/postal/compare` | Comparison tables |
| GET | `/postal/rankings/province` | Province rankings |
| GET | `/postal/rankings/city` | City rankings |
| GET | `/postal/ui/{page}` | Dashboard HTML |

---

## Configuring scores

Edit `config/scoring_weights.yaml` (weights must sum to 1.0), then rebuild.  
See **`docs/SCORING_METHODOLOGY.md`** for every formula.

---

## Official dataset notes

Profiles in `config/official_companies.yaml` are **curated public reference** records (`data_quality: curated_v1`) covering Tipax, Chapar, Post, Mahex, AloPeyk, Pishro. Refresh tariffs/hours from primary sources as they change; the pipeline treats them as inputs to scoring & comparison, not as scraped reviews.
