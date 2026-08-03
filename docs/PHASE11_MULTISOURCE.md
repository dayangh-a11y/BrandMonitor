# Phase 11 — Multi-Source Data Collection

## Goal

Clean multi-brand datasets for **Chapar, Post, Mahex, AloPeyk** with NLP enrichment and dedupe. No dashboards/charts.

## Commands

```bash
# Bounded Maps collection (major cities + sample provinces)
FAST_DISCOVER=true python3 scripts/collect_phase11_brands.py \
  --db data/phase11_multisource.db \
  --max-branches 25 \
  --max-reviews-per-branch 15

# Build clean CSVs (also reads analytics_demo Chapar if present)
python3 scripts/build_phase11_dataset.py \
  --dbs data/phase11_multisource.db data/analytics_demo.db \
  --brands Chapar Post Mahex AloPeyk \
  --out-dir /opt/cursor/artifacts/phase11_dataset
```

## Outputs

- `brand_summary.csv`
- `branch_summary.csv`
- `reviews_clean.csv`
- `entities.csv`
- `complaints.csv`
- `dashboard_dataset.csv` (flat analytics table — not a UI)
- `coverage_report.json`

## Sources

| Source | Status |
|--------|--------|
| Google Maps | Implemented |
| بلد / نشان / official / complaints / news | Stubs (`collectors/phase11/sources.py`) |

## NLP

Rule-based (`collectors/phase11/nlp.py`): sentiment, emotion, complaint_category, urgency, confidence_score, light entity extraction. Near-duplicate drop at >90% text similarity.
