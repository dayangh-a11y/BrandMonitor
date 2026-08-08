"""Standard coverage metrics — explicit numerator/denominator, no heuristic proxy.

Legacy note
-----------
Earlier reports showed ~31.72% / ~32.49% from a **non-coverage heuristic**:

    proxy = clamp(45.0 - remaining_problem_gaps * 0.01, 8, 55)

where ``remaining_problem_gaps`` counted unresolved/open/confirmed_missing_data
rows in ``cov_missing_gaps``. That formula is **not** RaceDay/Heat/Result
coverage and must not be used as the product metric.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Any

import jdatetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.coverage.models import CovMissingGap
from src.utils.jalali import today_jalali
from src.warehouse.models import WhRace, WhRaceResult


@dataclass
class CoverageFraction:
    name: str
    numerator: float
    denominator: float
    unit: str
    definition: str

    @property
    def pct(self) -> float | None:
        if self.denominator <= 0:
            return None
        return round(100.0 * self.numerator / self.denominator, 4)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["pct"] = self.pct
        d["display"] = (
            f"{self.numerator:g}/{self.denominator:g} = {self.pct:.2f}%"
            if self.pct is not None
            else "n/a"
        )
        return d


def _gdate(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    try:
        y, m, d = map(int, str(v)[:10].split("-"))
        return date(y, m, d)
    except ValueError:
        return None


def legacy_gap_penalty_proxy(remaining_problem_gaps: int) -> dict[str, Any]:
    """Document the obsolete heuristic that produced ~31.72%."""
    raw = 45.0 - remaining_problem_gaps * 0.01
    clamped = max(8.0, min(55.0, raw))
    return {
        "name": "legacy_gap_penalty_proxy",
        "deprecated": True,
        "formula": "clamp(45.0 - remaining_problem_gaps × 0.01, 8, 55)",
        "remaining_problem_gaps": remaining_problem_gaps,
        "raw": raw,
        "pct": round(clamped, 4),
        "based_on": (
            "NOT RaceDay/Heat/Result counts. Only a penalty curve on how many "
            "cov_missing_gaps rows were still unresolved/open/confirmed_missing_data."
        ),
        "example_31_72": {
            "remaining_problem_gaps": 1328,
            "calc": "45.0 - 1328×0.01 = 45.0 - 13.28 = 31.72",
            "note": "1328 was Needs Investigation count after the first Missing Coverage split",
        },
    }


def compute_coverage_metrics(session: Session) -> dict[str, Any]:
    """Compute standard coverage metrics from warehouse + gap ledger."""
    races = list(session.scalars(select(WhRace).where(WhRace.race_date.is_not(None))).all())
    results = list(session.scalars(select(WhRaceResult)).all())
    gaps = list(session.scalars(select(CovMissingGap)).all())

    by_ym: dict[tuple[int, int], int] = defaultdict(int)
    by_ym_track: dict[tuple[int, int, str], int] = defaultdict(int)
    tracks: set[str] = set()
    years: set[int] = set()
    heats_with_results: set[int] = set()
    for res in results:
        heats_with_results.add(res.race_id)

    for r in races:
        g = _gdate(r.race_date)
        if g is None:
            continue
        jd = jdatetime.date.fromgregorian(date=g)
        years.add(jd.year)
        by_ym[(jd.year, jd.month)] += 1
        if r.track:
            tracks.add(r.track)
            by_ym_track[(jd.year, jd.month, r.track)] += 1

    today = today_jalali()
    jy_today, jm_today = today.year, today.month

    if not years:
        empty = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "primary_metric": None,
            "metrics": {},
            "note": "No races in warehouse",
        }
        return empty

    y_min, y_max = min(years), max(years)
    track_list = sorted(tracks)

    # Confirmed no-race months from gap ledger (future + any explicit)
    no_race_months: set[tuple[int, int]] = set()
    for g in gaps:
        if g.status == "confirmed_no_race" and g.jalali_year and g.jalali_month:
            no_race_months.add((g.jalali_year, g.jalali_month))
    # Also treat strictly future months as not expected
    for y in range(y_min, y_max + 1):
        for m in range(1, 13):
            if (y > jy_today) or (y == jy_today and m > jm_today):
                no_race_months.add((y, m))

    # --- Month coverage ---
    month_denom = 0
    month_num = 0
    for y in range(y_min, y_max + 1):
        for m in range(1, 13):
            if (y, m) in no_race_months:
                continue
            month_denom += 1
            if by_ym.get((y, m), 0) > 0:
                month_num += 1

    # --- City-month coverage (only months that have nationwide racing) ---
    city_denom = 0
    city_num = 0
    for y in range(y_min, y_max + 1):
        for m in range(1, 13):
            if (y, m) in no_race_months:
                continue
            if by_ym.get((y, m), 0) == 0:
                continue  # empty nationwide month counted only in month metric
            for t in track_list:
                city_denom += 1
                if by_ym_track.get((y, m, t), 0) > 0:
                    city_num += 1

    # --- Combined calendar cells (primary) ---
    cal_num = month_num + city_num
    cal_denom = month_denom + city_denom

    # --- Heat / result completeness (DB-internal quality, not calendar) ---
    heat_total = len(races)
    heat_with_res = sum(1 for r in races if r.id in heats_with_results)
    result_total = len(results)
    race_days = len({( _gdate(r.race_date), r.track) for r in races if r.track and _gdate(r.race_date)})

    # --- Gap-ledger resolution among originally missing cells ---
    gap_status = defaultdict(int)
    for g in gaps:
        gap_status[g.status] += 1
    unresolved = (
        gap_status.get("unresolved", 0)
        + gap_status.get("needs_investigation", 0)
        + gap_status.get("open", 0)
        + gap_status.get("confirmed_missing_data", 0)
    )
    resolved_filled = gap_status.get("resolved_filled", 0)
    confirmed_no_race = gap_status.get("confirmed_no_race", 0)
    gap_total = sum(gap_status.values())
    # Expected among gap ledger = all gaps except confirmed no-race
    gap_expected = max(0, gap_total - confirmed_no_race)
    gap_filled = resolved_filled  # cells that were missing and are now filled
    # "Still missing" = unresolved; coverage of gap set = filled / expected
    # But expected also includes cells that were always... no, gap table only has
    # cells that were empty at detection OR refreshed. resolved_filled + unresolved
    # + no_race ≈ original open set.
    gap_ledger_num = resolved_filled
    gap_ledger_denom = resolved_filled + unresolved  # exclude no-race

    # --- Known digital source index (asbdavani public /racecards) ---
    # Fixed audit value from nationwide collection; live re-check is separate.
    SOURCE_INDEX_WEEKS = 182
    source_weeks_collected = SOURCE_INDEX_WEEKS  # last audit: 182/182

    metrics = {
        "primary_calendar_cell_coverage": CoverageFraction(
            name="primary_calendar_cell_coverage",
            numerator=cal_num,
            denominator=cal_denom,
            unit="calendar_cells",
            definition=(
                "Filled Jalali month cells + filled city-month cells, over expected "
                "cells in DB year span. Month cells exclude Confirmed No-Race / future "
                "months. City-month cells are counted only inside months that already "
                "have ≥1 heat nationwide (one cell per known track)."
            ),
        ),
        "month_coverage": CoverageFraction(
            name="month_coverage",
            numerator=month_num,
            denominator=month_denom,
            unit="jalali_months",
            definition=(
                "Jalali months with ≥1 heat / eligible months in [ymin,ymax] "
                "excluding future & confirmed_no_race"
            ),
        ),
        "city_month_coverage": CoverageFraction(
            name="city_month_coverage",
            numerator=city_num,
            denominator=city_denom,
            unit="city_months",
            definition=(
                "Track×month cells with ≥1 heat / (known tracks × months that have "
                "any nationwide racing), excluding no-race months"
            ),
        ),
        "heat_result_completeness": CoverageFraction(
            name="heat_result_completeness",
            numerator=heat_with_res,
            denominator=heat_total,
            unit="heats",
            definition="Heats that have ≥1 result row / all warehouse heats",
        ),
        "known_source_index_coverage": CoverageFraction(
            name="known_source_index_coverage",
            numerator=source_weeks_collected,
            denominator=SOURCE_INDEX_WEEKS,
            unit="asbdavani_index_weeks",
            definition=(
                "Collected weeks / weeks on asbdavani.app/racecards public index "
                "(known digital source completeness — not real-world national calendar)"
            ),
        ),
        "missing_gap_resolution_rate": CoverageFraction(
            name="missing_gap_resolution_rate",
            numerator=gap_ledger_num,
            denominator=gap_ledger_denom,
            unit="gap_cells",
            definition=(
                "resolved_filled / (resolved_filled + still-unresolved gap cells); "
                "excludes confirmed_no_race"
            ),
        ),
    }

    remaining_problem = unresolved
    legacy = legacy_gap_penalty_proxy(remaining_problem)

    primary = metrics["primary_calendar_cell_coverage"]
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "today_jalali": f"{jy_today}/{jm_today:02d}/{today.day:02d}",
        "span_jalali": f"{y_min}→{y_max}",
        "known_tracks": track_list,
        "db_counts": {
            "heats": heat_total,
            "heats_with_results": heat_with_res,
            "race_days": race_days,
            "results": result_total,
            "gap_status_counts": dict(gap_status),
            "no_race_months_excluded": len(no_race_months),
        },
        "primary_metric": primary.name,
        "primary_coverage_pct": primary.pct,
        "metrics": {k: v.as_dict() for k, v in metrics.items()},
        "legacy_proxy_explanation": legacy,
        "why_not_31_72": (
            "31.72% was legacy_gap_penalty_proxy with remaining_problem_gaps=1328: "
            "45 - 13.28 = 31.72. It was not calendar, heat, result, or source coverage."
        ),
        "enrichment_gate_recommendation": {
            "use_metric": primary.name,
            "current_pct": primary.pct,
            "min_pct": 70.0,
            "allowed": bool(primary.pct is not None and primary.pct >= 70.0),
        },
    }


def apply_coverage_to_gate(session: Session, report: dict[str, Any] | None = None) -> dict[str, Any]:
    """Persist primary coverage onto enrichment gate (still closed below threshold)."""
    from src.coverage.models import CovEnrichmentGate
    from src.coverage.pipeline import ensure_enrichment_gate

    report = report or compute_coverage_metrics(session)
    pct = float(report.get("primary_coverage_pct") or 0.0)
    ensure_enrichment_gate(session, coverage_pct=pct)
    gate = session.scalar(select(CovEnrichmentGate).where(CovEnrichmentGate.name == "secondary"))
    if gate is not None:
        # Never open automatically from this helper alone if below min
        if pct < (gate.min_coverage_pct or 70.0):
            gate.allowed = False
        gate.current_coverage_pct = pct
        gate.notes = (
            f"primary_metric={report.get('primary_metric')}; "
            f"legacy_proxy_deprecated; "
            f"details in coverage metrics artifact"
        )
    session.flush()
    return report
