#!/usr/bin/env python3
"""Coverage logic audit + recalculation (no extract/merge)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy import func, select

from src.coverage.metrics import (
    apply_coverage_to_gate,
    compute_coverage_metrics,
    legacy_gap_penalty_proxy,
)
from src.coverage.models import CovEnrichmentGate, CovMissingGap
from src.database import init_db, session_scope

ART = Path("/opt/cursor/artifacts")
DB = os.environ.get("DATABASE_URL", "sqlite:////workspace/output/historical/horse_racing.db")

# Values published before this audit fix (from coverage_metrics.json / prior reports)
OLD = {
    "Primary Calendar Cell": {"pct": 23.6663, "fraction": "763/3224"},
    "Month Coverage": {"pct": 80.9769, "fraction": "315/389"},
    "City-Month Coverage": {"pct": 15.8025, "fraction": "448/2835"},
    "Heat→Result Completeness": {"pct": 97.8071, "fraction": "3256/3329"},
    "Known Source Index": {"pct": 100.0, "fraction": "182/182"},
    "Missing-Gap Resolution": {"pct": 16.0966, "fraction": "240/1491"},
}


def main() -> int:
    ART.mkdir(parents=True, exist_ok=True)
    init_db(url=DB)

    with session_scope() as session:
        rem = (
            session.scalar(
                select(func.count())
                .select_from(CovMissingGap)
                .where(
                    CovMissingGap.status.in_(
                        [
                            "unresolved",
                            "needs_investigation",
                            "confirmed_missing_data",
                            "open",
                        ]
                    )
                )
            )
            or 0
        )
        report = compute_coverage_metrics(session)
        apply_coverage_to_gate(session, report)
        gate = session.scalar(
            select(CovEnrichmentGate).where(CovEnrichmentGate.name == "secondary")
        )
        report["legacy_at_31_72_moment"] = legacy_gap_penalty_proxy(1328)
        report["legacy_if_recomputed_now"] = legacy_gap_penalty_proxy(int(rem))
        report["enrichment_gate"] = {
            "allowed": bool(gate.allowed) if gate else False,
            "current_coverage_pct": gate.current_coverage_pct if gate else None,
            "min_coverage_pct": gate.min_coverage_pct if gate else 70.0,
            "notes": gate.notes if gate else None,
        }
        session.commit()

    m = report["metrics"]
    mapping = {
        "Primary Calendar Cell": "primary_calendar_cell_coverage",
        "Month Coverage": "month_coverage",
        "City-Month Coverage": "city_month_coverage",
        "Heat→Result Completeness": "heat_result_completeness",
        "Known Source Index": "known_source_index_coverage",
        "Missing-Gap Resolution": "missing_gap_resolution_rate",
    }

    rows = []
    for label, key in mapping.items():
        old = OLD[label]
        new = m[key]
        diff = round(float(new["pct"]) - float(old["pct"]), 4)
        if label == "Primary Calendar Cell":
            reason = (
                "تعریف اصلاح شد: حذف double-count ماه+شهر×ماه "
                f"(مخرج {old['fraction']} → {new['numerator']}/{new['denominator']}); "
                "سلول خالی بدون شاهد = UNRESOLVED نه Missing Data"
            )
        elif abs(diff) < 1e-9:
            reason = "محاسبه مجدد با همان تعریف — بدون اختلاف"
        else:
            reason = "تغییر جزئی به دلیل تعریف class-based"
        rows.append(
            {
                "Metric": label,
                "Old Value": old["pct"],
                "Recalculated Value": new["pct"],
                "Difference": diff,
                "علت اختلاف": reason,
                "Old Fraction": old["fraction"],
                "New Fraction": f"{new['numerator']}/{new['denominator']}",
            }
        )

    # Extra honesty metrics
    rows.append(
        {
            "Metric": "Proven Obligation Coverage (new)",
            "Old Value": None,
            "Recalculated Value": m["proven_obligation_coverage"]["pct"],
            "Difference": None,
            "علت اختلاف": (
                "متریک جدید: CONFIRMED_RACE/(RACE+MISSING_DATA)؛ "
                "UNRESOLVED از مخرج خارج است"
            ),
            "Old Fraction": None,
            "New Fraction": (
                f"{m['proven_obligation_coverage']['numerator']}/"
                f"{m['proven_obligation_coverage']['denominator']}"
            ),
        }
    )
    rows.append(
        {
            "Metric": "Deprecated Mixed Month+City (audit)",
            "Old Value": OLD["Primary Calendar Cell"]["pct"],
            "Recalculated Value": m["deprecated_mixed_month_plus_city"]["pct"],
            "Difference": round(
                float(m["deprecated_mixed_month_plus_city"]["pct"])
                - float(OLD["Primary Calendar Cell"]["pct"]),
                4,
            ),
            "علت اختلاف": "همان تعریف قدیمی مخلوط — فقط برای شفافیت audit",
            "Old Fraction": OLD["Primary Calendar Cell"]["fraction"],
            "New Fraction": (
                f"{m['deprecated_mixed_month_plus_city']['numerator']}/"
                f"{m['deprecated_mixed_month_plus_city']['denominator']}"
            ),
        }
    )

    out = {
        "generated_at_utc": report["generated_at_utc"],
        "today_jalali": report["today_jalali"],
        "span_jalali": report["span_jalali"],
        "known_tracks": report["known_tracks"],
        "includes_1405": report["includes_1405"],
        "classification": report["classification"],
        "formulas": {
            "Primary Calendar Cell": {
                "numerator": "CONFIRMED_RACE cells in deduped universe",
                "denominator": "CONFIRMED_RACE + MISSING_DATA + UNRESOLVED",
                "tables": "wh_races.race_date,track; cov_missing_gaps.status",
                "universe": (
                    "city-month per known track for months with ≥1 nationwide heat; "
                    "one nationwide month cell for empty eligible months"
                ),
                "years": report["span_jalali"],
                "cities": report["known_tracks"],
                "year_1405": report["includes_1405"],
                "only_months_with_races": "for city-month branch yes; empty months kept as month cells",
                "empty_as_missing": False,
                "empty_as_unresolved": True,
                "no_race_separated": True,
            },
            "Month Coverage": {
                "numerator": "CONFIRMED_RACE months",
                "denominator": "RACE + MISSING_DATA + UNRESOLVED months",
                "tables": "wh_races; cov_missing_gaps",
                "years": report["span_jalali"],
                "cities": "n/a",
                "year_1405": report["includes_1405"],
                "only_months_with_races_in_denom": False,
                "empty_as_missing": False,
                "no_race_separated": True,
            },
            "City-Month Coverage": {
                "numerator": "CONFIRMED_RACE city-months",
                "denominator": "RACE + MISSING_DATA + UNRESOLVED city-months",
                "tables": "wh_races.race_date,track; cov_missing_gaps",
                "years": report["span_jalali"],
                "cities": report["known_tracks"],
                "only_months_with_races_in_denom": True,
                "empty_city_as_missing": False,
                "empty_city_as_unresolved": True,
                "no_race_separated": True,
            },
            "Heat→Result Completeness": {
                "numerator": "wh_races with ≥1 wh_race_results",
                "denominator": "count(wh_races)",
                "tables": "wh_races.id; wh_race_results.race_id",
            },
            "Known Source Index": {
                "numerator": "collected_race_weeks from coverage_denominator_audit.json",
                "denominator": "official_race_weeks_on_website_index from same artifact",
                "tables": "artifact (not live DB)",
            },
            "Missing-Gap Resolution": {
                "numerator": "cov_missing_gaps.status=resolved_filled",
                "denominator": "resolved_filled + unresolved/needs_investigation/open/confirmed_missing_data",
                "tables": "cov_missing_gaps.status",
                "no_race_separated": True,
            },
        },
        "comparison_table": rows,
        "enrichment_gate": report["enrichment_gate"],
        "full_metrics": report,
    }

    (ART / "coverage_metrics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (ART / "coverage_logic_audit.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    md = [
        "# Coverage Logic Audit",
        "",
        f"Today: **{report['today_jalali']}** · Span: **{report['span_jalali']}**",
        "",
        "## Classification — Primary universe (deduped)",
        "",
        "| Class | Count |",
        "|---|---:|",
    ]
    for k in [
        "CONFIRMED_RACE",
        "CONFIRMED_NO_RACE",
        "MISSING_DATA",
        "UNRESOLVED",
    ]:
        md.append(
            f"| {k} | {report['classification']['primary_universe'].get(k, 0)} |"
        )
    md += [
        f"| **Total** | **{report['classification']['primary_universe_size']}** |",
        "",
        "## Classification — City-Month",
        "",
        "| Class | Count |",
        "|---|---:|",
    ]
    for k in [
        "CONFIRMED_RACE",
        "CONFIRMED_NO_RACE",
        "MISSING_DATA",
        "UNRESOLVED",
    ]:
        md.append(
            f"| {k} | {report['classification']['city_month_universe'].get(k, 0)} |"
        )
    md += [
        "",
        "## Metric | Old Value | Recalculated Value | Difference | علت اختلاف",
        "",
        "| Metric | Old Value | Recalculated Value | Difference | علت اختلاف |",
        "|---|---:|---:|---:|---|",
    ]
    for r in rows:
        ov = "—" if r["Old Value"] is None else f"{r['Old Value']:.4f}"
        rv = "—" if r["Recalculated Value"] is None else f"{r['Recalculated Value']:.4f}"
        df = "—" if r["Difference"] is None else f"{r['Difference']:.4f}"
        md.append(
            f"| {r['Metric']} | {ov} | {rv} | {df} | {r['علت اختلاف']} |"
        )
    md += [
        "",
        f"Enrichment gate: allowed={report['enrichment_gate']['allowed']} "
        f"pct={report['enrichment_gate']['current_coverage_pct']} "
        f"min={report['enrichment_gate']['min_coverage_pct']}",
        "",
    ]
    (ART / "coverage_logic_audit.md").write_text("\n".join(md), encoding="utf-8")
    (ART / "coverage_metrics.md").write_text("\n".join(md), encoding="utf-8")

    print(json.dumps({"comparison_table": rows, "classification": report["classification"], "gate": report["enrichment_gate"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
