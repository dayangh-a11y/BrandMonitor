# Standardization Roadmap (Platform v3.0.0)

Fifteen modules that make analytics **reproducible, explainable, and
statistically valid**. Package: `src/standardization/`.

## Layer separation (Module 15)

```
RAW → METRICS → FEATURES → PREDICTIONS → RECOMMENDATIONS
```

Never mix these layers in one payload or table.

## Modules

| ID | Module | Implementation |
|----|--------|----------------|
| M01 | Data Quality | `data_quality.py` → `std_dq_reports` |
| M02 | Entity Resolution | `entities.py` → `std_entities` / aliases; writes `canonical_entity_id` |
| M03 | Season Engine | `seasons.py` → `std_seasons` (`season_id`, dates, track, country, year) |
| M04 | Race Classification | `race_classification.py` → `std_race_classifications` |
| M05 | Performance Metrics | `metrics_catalog.py` — mathematical definitions |
| M06 | Ranking Engine | `ranking_contracts.py` — eligibility, formula, tie-break, min starts/confidence, version |
| M07 | Explainability | `explain.py` — rule, formula, metrics, rows, confidence, missing, warnings |
| M08 | Confidence Engine | `confidence.py` — Very High…Very Low from sample + missing + completeness |
| M09 | Question Engine | `questions.py` — NL/slug → rule → SQL → metrics → explanation |
| M10 | Validation Engine | `validation.py` — single-start, missing, abnormal earnings, impossible stats |
| M11 | Benchmark Engine | `benchmarks.py` → `std_benchmarks` |
| M12 | Version Control | `versions.py` → `std_version_registry` |
| M13 | Audit Log | `audit.py` → `std_audit_log` |
| M14 | Feature Store | `feature_store.py` → `std_feature_store` (store once, reuse) |
| M15 | AI Readiness | `ai_layers.py` — layer contracts + readiness checklist |

## CLI

```bash
python main.py init-db
python main.py analytics build --course gonbad-kavous --min-starts 5
python main.py std build --course gonbad-kavous
python main.py std report
python main.py std dq
python main.py std metrics
python main.py std contracts
python main.py std validate --scope season
python main.py std ask -q "best horse of the season" -n 10
python main.py quality-report   # includes warehouse DQ (Module 1)
```

## Season Best under Module 6 + 10

If all horses have one start, Question Engine / analytics gate returns
**INSUFFICIENT DATA** — never a prize-money “best horse”.

## Tables (`std_*`)

- `std_entities`, `std_entity_aliases`
- `std_seasons`
- `std_race_classifications`
- `std_version_registry`
- `std_audit_log`
- `std_feature_store`
- `std_dq_reports`
- `std_benchmarks`
