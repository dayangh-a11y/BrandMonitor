#!/usr/bin/env python3
"""Build the full Coverage Matrix (year × month × city). Read-only — no enrichment."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.coverage.matrix import build_coverage_matrix, write_matrix_artifacts
from src.coverage.metrics import apply_coverage_to_gate, compute_coverage_metrics
from src.coverage.models import CovEnrichmentGate
from sqlalchemy import select


def main() -> int:
    db = ROOT / "output" / "historical" / "horse_racing.db"
    engine = create_engine(f"sqlite:///{db}")
    with Session(engine) as session:
        report = build_coverage_matrix(session)
        paths = write_matrix_artifacts(report)

        # Align product Coverage + gate with proven formula on full matrix
        cov = report["coverage"]
        metrics_report = compute_coverage_metrics(session)
        # Override primary to matrix proven Coverage
        metrics_report["primary_metric"] = "coverage_matrix_proven"
        metrics_report["primary_coverage_pct"] = cov["pct"]
        metrics_report["coverage_matrix"] = {
            "status_counts": report["status_counts"],
            "total_cells": report["total_cells"],
            "coverage": cov,
            "artifacts": paths,
        }
        metrics_report["enrichment_gate_recommendation"] = {
            "use_metric": "coverage_matrix_proven",
            "formula": cov["formula"],
            "current_pct": cov["pct"],
            "min_pct": 70.0,
            "allowed": bool(cov["pct"] is not None and cov["pct"] >= 70.0),
            "note": "Gate still uses proven Coverage; enrichment blocked until matrix obligations met & ≥70%.",
        }
        apply_coverage_to_gate(session, metrics_report)
        # Force gate notes/pct to matrix proven.
        # Keep enrichment CLOSED while any MISSING_DATA remains (proven races not yet in WH),
        # even if proven Coverage ≥ min — coverage-first lock.
        gate = session.scalar(
            select(CovEnrichmentGate).where(CovEnrichmentGate.name == "secondary")
        )
        md_left = int(report["status_counts"].get("MISSING_DATA") or 0)
        if gate is not None:
            gate.current_coverage_pct = float(cov["pct"] or 0.0)
            meets_pct = (cov["pct"] or 0) >= (gate.min_coverage_pct or 70)
            gate.allowed = bool(meets_pct and md_left == 0)
            gate.notes = (
                "primary_metric=coverage_matrix_proven; "
                "Coverage=CONFIRMED_RACE/(CONFIRMED_RACE+MISSING_DATA); "
                f"MISSING_DATA_open={md_left}; "
                "UNRESOLVED excluded; empty≠no-race; "
                "enrichment requires pct≥min AND zero MISSING_DATA"
            )
        session.commit()

        gate_out = {
            "allowed": bool(gate.allowed) if gate else False,
            "current_coverage_pct": gate.current_coverage_pct if gate else None,
            "min_coverage_pct": gate.min_coverage_pct if gate else 70.0,
            "notes": gate.notes if gate else None,
        }

    out = {
        "status_counts": report["status_counts"],
        "total_cells": report["total_cells"],
        "coverage": report["coverage"],
        "span_jalali": report["span_jalali"],
        "cities": report["cities"],
        "artifacts": paths,
        "enrichment_gate": gate_out,
        "enrichment_blocked": True,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
