#!/usr/bin/env python3
"""Explain legacy 31.72% proxy and compute standard coverage metrics."""

from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy.orm import Session

from src.coverage.metrics import apply_coverage_to_gate, compute_coverage_metrics, legacy_gap_penalty_proxy
from src.coverage.models import CovEnrichmentGate, CovMissingGap
from src.database import init_db, session_scope
from sqlalchemy import func, select

ART = Path("/opt/cursor/artifacts")
DB = os.environ.get("DATABASE_URL", "sqlite:////workspace/output/historical/horse_racing.db")


def main() -> int:
    ART.mkdir(parents=True, exist_ok=True)
    init_db(url=DB)

    with session_scope() as session:
        rem = session.scalar(
            select(func.count())
            .select_from(CovMissingGap)
            .where(
                CovMissingGap.status.in_(
                    ["unresolved", "needs_investigation", "confirmed_missing_data", "open"]
                )
            )
        ) or 0
        # Historical 31.72 used 1328 NI cells specifically
        legacy_then = legacy_gap_penalty_proxy(1328)
        legacy_now = legacy_gap_penalty_proxy(int(rem))
        report = compute_coverage_metrics(session)
        apply_coverage_to_gate(session, report)
        gate = session.scalar(select(CovEnrichmentGate).where(CovEnrichmentGate.name == "secondary"))
        report["legacy_at_31_72_moment"] = legacy_then
        report["legacy_if_recomputed_now"] = legacy_now
        report["enrichment_gate"] = {
            "allowed": bool(gate.allowed) if gate else False,
            "current_coverage_pct": gate.current_coverage_pct if gate else None,
            "min_coverage_pct": gate.min_coverage_pct if gate else 70.0,
            "notes": gate.notes if gate else None,
        }
        session.commit()

    (ART / "coverage_metrics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    primary = report["metrics"]["primary_calendar_cell_coverage"]
    month = report["metrics"]["month_coverage"]
    city = report["metrics"]["city_month_coverage"]
    heat = report["metrics"]["heat_result_completeness"]
    source = report["metrics"]["known_source_index_coverage"]
    gapr = report["metrics"]["missing_gap_resolution_rate"]

    md = f"""# Coverage Metric — Formula & Numbers

## 1) What was 31.72%?

**Not real coverage.** It was a deprecated heuristic:

```text
proxy = clamp(45.0 − remaining_problem_gaps × 0.01, 8, 55)
```

At the Missing-Coverage classification moment:

| Symbol | Meaning | Value |
|---|---|---:|
| remaining_problem_gaps | Needs Investigation cells still open | **1328** |
| raw | 45.0 − 1328×0.01 | **31.72** |
| clamp | max(8, min(55, raw)) | **31.72%** |

- **Numerator / denominator:** none — not a fraction of RaceDays, Heats, Results, or cells.
- **Based on:** only a penalty on how many `cov_missing_gaps` rows were still “problem” statuses.
- Later with 1251 unresolved: `45 − 12.51 = 32.49%` (same fake curve).

## 2) Standard Coverage Metric (now)

**Primary metric = Calendar Cell Coverage**

```text
Coverage = Filled_Cells / Expected_Cells

Filled_Cells   = filled_jalali_months + filled_city_months
Expected_Cells = eligible_jalali_months + eligible_city_months
```

Definitions:
- **eligible_jalali_months**: every month in DB Jalali span except Confirmed No-Race / future months
- **filled_jalali_months**: eligible months with ≥1 heat
- **eligible_city_months**: for each eligible month that already has nationwide racing, one cell per known track
- **filled_city_months**: those cells with ≥1 heat for that track

### Live numbers

| Metric | Formula | Value |
|---|---|---|
| **Primary Calendar Cell Coverage** | `{primary['numerator']}/{primary['denominator']}` | **{primary['pct']:.2f}%** |
| Month Coverage | `{month['numerator']}/{month['denominator']}` | **{month['pct']:.2f}%** |
| City-Month Coverage | `{city['numerator']}/{city['denominator']}` | **{city['pct']:.2f}%** |
| Heat→Result Completeness | `{heat['numerator']}/{heat['denominator']}` | **{heat['pct']:.2f}%** |
| Known Source Index (asbdavani /racecards) | `{source['numerator']}/{source['denominator']}` | **{source['pct']:.2f}%** |
| Missing-Gap Resolution Rate | `{gapr['numerator']}/{gapr['denominator']}` | **{gapr['pct']:.2f}%** |

Span: **{report['span_jalali']}** · Tracks: {len(report['known_tracks'])} · Today: **{report['today_jalali']}**

## 3) What each metric is based on

| Metric | Race Day | Heat | Result | Month/City cells | Source index |
|---|:---:|:---:|:---:|:---:|:---:|
| Primary Calendar Cell | (via heats) | yes | no | **yes** | no |
| Month Coverage | (via heats) | yes | no | month only | no |
| City-Month Coverage | (via heats) | yes | no | city×month | no |
| Heat→Result Completeness | no | yes | yes | no | no |
| Known Source Index | week≈race-day | yes | no | no | **yes** |
| Legacy 31.72 proxy | no | no | no | gap-row count only | no |

## 4) Enrichment gate

Gate now stores **primary calendar cell coverage** = **{primary['pct']:.2f}%** (min 70%). Allowed = **{report['enrichment_gate']['allowed']}**.
"""
    (ART / "coverage_metrics.md").write_text(md, encoding="utf-8")
    print(json.dumps({
        "legacy_31_72": legacy_then,
        "primary": primary,
        "month": month,
        "city_month": city,
        "heat_result": heat,
        "source_index": source,
        "gap_resolution": gapr,
        "gate": report["enrichment_gate"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
