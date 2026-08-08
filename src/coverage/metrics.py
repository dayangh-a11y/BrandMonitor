"""Standard coverage metrics — explicit numerator/denominator.

Product Coverage (authoritative)
--------------------------------
Full matrix: Jalali year × month × city (see ``src/coverage/matrix.py``).

```text
Coverage = CONFIRMED_RACE / (CONFIRMED_RACE + MISSING_DATA)
```

- Only cells where a race is **proven** to have occurred (captured or still missing).
- UNRESOLVED excluded (empty alone ≠ No-Race and ≠ Missing Data).
- CONFIRMED_NO_RACE is proven absence — reported separately, not Coverage debt.

Companion / audit metrics
-------------------------
- Grid fill on deduped calendar universe (includes UNRESOLVED in denom).
- Month / city-month / heat→result / source-index / gap-resolution.

Deprecated: ``clamp(45 - gaps*0.01)`` (~31.72%) and mixed month+city fractions.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

import jdatetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.coverage.models import CovMissingGap
from src.utils.jalali import today_jalali
from src.warehouse.models import WhRace, WhRaceResult

CellClass = Literal[
    "CONFIRMED_RACE",
    "CONFIRMED_NO_RACE",
    "MISSING_DATA",
    "UNRESOLVED",
]

ART = Path("/opt/cursor/artifacts")


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
        },
    }


def _build_indexes(session: Session) -> dict[str, Any]:
    races = list(session.scalars(select(WhRace).where(WhRace.race_date.is_not(None))).all())
    results = list(session.scalars(select(WhRaceResult)).all())
    gaps = list(session.scalars(select(CovMissingGap)).all())

    by_ym: dict[tuple[int, int], int] = defaultdict(int)
    by_ym_track: dict[tuple[int, int, str], int] = defaultdict(int)
    tracks: set[str] = set()
    years: set[int] = set()
    heats_with_results = {res.race_id for res in results}

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

    gap_month: dict[tuple[int, int], str] = {}
    gap_city: dict[tuple[int, int, str], str] = {}
    gap_status: Counter = Counter()
    for g in gaps:
        gap_status[g.status] += 1
        if g.jalali_year is None or g.jalali_month is None:
            continue
        if g.scope_type == "month":
            gap_month[(g.jalali_year, g.jalali_month)] = g.status
        elif g.scope_type == "city_month" and g.track:
            gap_city[(g.jalali_year, g.jalali_month, g.track)] = g.status

    return {
        "races": races,
        "results": results,
        "by_ym": by_ym,
        "by_ym_track": by_ym_track,
        "tracks": sorted(tracks),
        "years": years,
        "heats_with_results": heats_with_results,
        "gap_month": gap_month,
        "gap_city": gap_city,
        "gap_status": gap_status,
    }


def _is_future(y: int, m: int, jy_today: int, jm_today: int) -> bool:
    return (y > jy_today) or (y == jy_today and m > jm_today)


def _classify_month(
    y: int,
    m: int,
    *,
    by_ym: dict,
    gap_month: dict,
    jy_today: int,
    jm_today: int,
) -> tuple[CellClass, str]:
    heats = by_ym.get((y, m), 0)
    status = gap_month.get((y, m))
    if heats > 0:
        return "CONFIRMED_RACE", f"heats_in_db={heats}"
    if status == "confirmed_no_race" or _is_future(y, m, jy_today, jm_today):
        return "CONFIRMED_NO_RACE", "future_or_gap_confirmed_no_race"
    if status == "confirmed_missing_data":
        return "MISSING_DATA", "gap_confirmed_missing_data"
    return "UNRESOLVED", f"empty_no_proof status={status}"


def _classify_city(
    y: int,
    m: int,
    track: str,
    *,
    by_ym_track: dict,
    gap_month: dict,
    gap_city: dict,
    jy_today: int,
    jm_today: int,
) -> tuple[CellClass, str]:
    heats = by_ym_track.get((y, m, track), 0)
    status = gap_city.get((y, m, track))
    if heats > 0:
        return "CONFIRMED_RACE", f"heats_in_db={heats}"
    if _is_future(y, m, jy_today, jm_today) or gap_month.get((y, m)) == "confirmed_no_race":
        return "CONFIRMED_NO_RACE", "month_is_no_race_or_future"
    if status == "confirmed_no_race":
        return "CONFIRMED_NO_RACE", "gap_confirmed_no_race"
    if status == "confirmed_missing_data":
        return "MISSING_DATA", "gap_confirmed_missing_data"
    return "UNRESOLVED", f"empty_no_proof status={status}"


def _fraction_from_classes(counter: Counter, *, mode: str) -> tuple[int, int]:
    race = int(counter.get("CONFIRMED_RACE", 0))
    missing = int(counter.get("MISSING_DATA", 0))
    unresolved = int(counter.get("UNRESOLVED", 0))
    if mode == "grid_fill":
        return race, race + missing + unresolved
    if mode == "proven":
        return race, race + missing
    raise ValueError(mode)


def compute_coverage_metrics(session: Session) -> dict[str, Any]:
    """Compute standard coverage metrics from warehouse + gap ledger."""
    idx = _build_indexes(session)
    races = idx["races"]
    by_ym = idx["by_ym"]
    by_ym_track = idx["by_ym_track"]
    track_list = idx["tracks"]
    years: set[int] = idx["years"]
    heats_with_results = idx["heats_with_results"]
    gap_month = idx["gap_month"]
    gap_city = idx["gap_city"]
    gap_status: Counter = idx["gap_status"]

    today = today_jalali()
    jy_today, jm_today = today.year, today.month

    if not years:
        return {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "primary_metric": None,
            "metrics": {},
            "note": "No races in warehouse",
        }

    y_min, y_max = min(years), max(years)

    # Eligible months (exclude future / confirmed no-race)
    no_race_months: set[tuple[int, int]] = set()
    for (y, m), st in gap_month.items():
        if st == "confirmed_no_race":
            no_race_months.add((y, m))
    for y in range(y_min, y_max + 1):
        for m in range(1, 13):
            if _is_future(y, m, jy_today, jm_today):
                no_race_months.add((y, m))

    eligible_months = [
        (y, m)
        for y in range(y_min, y_max + 1)
        for m in range(1, 13)
        if (y, m) not in no_race_months
    ]

    # --- Build corrected primary universe (no double count) ---
    primary_cells: list[dict[str, Any]] = []
    for y, m in eligible_months:
        if by_ym.get((y, m), 0) > 0:
            for t in track_list:
                cls, why = _classify_city(
                    y,
                    m,
                    t,
                    by_ym_track=by_ym_track,
                    gap_month=gap_month,
                    gap_city=gap_city,
                    jy_today=jy_today,
                    jm_today=jm_today,
                )
                primary_cells.append(
                    {
                        "cell_type": "city_month",
                        "jalali_year": y,
                        "jalali_month": m,
                        "city": t,
                        "class": cls,
                        "reason": why,
                        "heats": by_ym_track.get((y, m, t), 0),
                    }
                )
        else:
            cls, why = _classify_month(
                y,
                m,
                by_ym=by_ym,
                gap_month=gap_month,
                jy_today=jy_today,
                jm_today=jm_today,
            )
            primary_cells.append(
                {
                    "cell_type": "month",
                    "jalali_year": y,
                    "jalali_month": m,
                    "city": None,
                    "class": cls,
                    "reason": why,
                    "heats": 0,
                }
            )

    primary_class = Counter(c["class"] for c in primary_cells)
    p_num, p_den = _fraction_from_classes(primary_class, mode="grid_fill")
    proven_num, proven_den = _fraction_from_classes(primary_class, mode="proven")

    # --- Month coverage (eligible months only) ---
    month_cells = []
    for y, m in eligible_months:
        cls, why = _classify_month(
            y, m, by_ym=by_ym, gap_month=gap_month, jy_today=jy_today, jm_today=jm_today
        )
        month_cells.append(
            {
                "cell_type": "month",
                "jalali_year": y,
                "jalali_month": m,
                "city": None,
                "class": cls,
                "reason": why,
                "heats": by_ym.get((y, m), 0),
            }
        )
    month_class = Counter(c["class"] for c in month_cells)
    m_num, m_den = _fraction_from_classes(month_class, mode="grid_fill")

    # --- City-month coverage (only months with nationwide racing) ---
    city_cells = [
        c for c in primary_cells if c["cell_type"] == "city_month"
    ]
    # Also include city cells classification for active months only — already the case
    city_class = Counter(c["class"] for c in city_cells)
    c_num, c_den = _fraction_from_classes(city_class, mode="grid_fill")
    c_proven_num, c_proven_den = _fraction_from_classes(city_class, mode="proven")

    # --- Heat / result completeness ---
    heat_total = len(races)
    heat_with_res = sum(1 for r in races if r.id in heats_with_results)
    result_total = len(idx["results"])
    race_days = len(
        {
            (_gdate(r.race_date), r.track)
            for r in races
            if r.track and _gdate(r.race_date)
        }
    )

    # --- Gap-ledger resolution ---
    unresolved = (
        gap_status.get("unresolved", 0)
        + gap_status.get("needs_investigation", 0)
        + gap_status.get("open", 0)
        + gap_status.get("confirmed_missing_data", 0)
    )
    resolved_filled = gap_status.get("resolved_filled", 0)
    gap_ledger_num = resolved_filled
    gap_ledger_denom = resolved_filled + unresolved

    # --- Known digital source index (from last audit artifact if present) ---
    src_path = ART / "coverage_denominator_audit.json"
    source_weeks_collected = 182
    source_weeks_official = 182
    source_note = "fallback constants from last nationwide audit"
    if src_path.exists():
        try:
            sa = __import__("json").loads(src_path.read_text(encoding="utf-8"))
            source_weeks_collected = int(sa.get("collected_race_weeks") or 182)
            source_weeks_official = int(
                sa.get("official_race_weeks_on_website_index") or 182
            )
            source_note = "from coverage_denominator_audit.json (not live re-crawl)"
        except Exception:
            pass

    # Deprecated mixed primary (for comparison only)
    legacy_month_num = sum(1 for y, m in eligible_months if by_ym.get((y, m), 0) > 0)
    legacy_month_den = len(eligible_months)
    legacy_city_num = c_num
    legacy_city_den = c_den
    legacy_mixed_num = legacy_month_num + legacy_city_num
    legacy_mixed_den = legacy_month_den + legacy_city_den

    metrics = {
        "primary_calendar_cell_coverage": CoverageFraction(
            name="primary_calendar_cell_coverage",
            numerator=p_num,
            denominator=p_den,
            unit="calendar_cells_deduped",
            definition=(
                "CONFIRMED_RACE / (CONFIRMED_RACE + MISSING_DATA + UNRESOLVED) on the "
                "deduped calendar universe: city-month cells for months with nationwide "
                "racing; one nationwide month cell for empty eligible months. "
                "CONFIRMED_NO_RACE excluded. Empty without proof = UNRESOLVED, not Missing Data."
            ),
        ),
        "proven_obligation_coverage": CoverageFraction(
            name="proven_obligation_coverage",
            numerator=proven_num,
            denominator=proven_den,
            unit="proven_calendar_cells",
            definition=(
                "CONFIRMED_RACE / (CONFIRMED_RACE + MISSING_DATA). "
                "UNRESOLVED excluded from denominator (no invented expectations)."
            ),
        ),
        "month_coverage": CoverageFraction(
            name="month_coverage",
            numerator=m_num,
            denominator=m_den,
            unit="jalali_months",
            definition=(
                "CONFIRMED_RACE months / (RACE + MISSING_DATA + UNRESOLVED months); "
                "eligible months exclude future & confirmed_no_race"
            ),
        ),
        "city_month_coverage": CoverageFraction(
            name="city_month_coverage",
            numerator=c_num,
            denominator=c_den,
            unit="city_months",
            definition=(
                "CONFIRMED_RACE city-months / (RACE + MISSING_DATA + UNRESOLVED) "
                "inside months that already have nationwide racing"
            ),
        ),
        "city_month_proven_coverage": CoverageFraction(
            name="city_month_proven_coverage",
            numerator=c_proven_num,
            denominator=c_proven_den,
            unit="proven_city_months",
            definition="CONFIRMED_RACE / (CONFIRMED_RACE + MISSING_DATA) for city-months only",
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
            denominator=source_weeks_official,
            unit="asbdavani_index_weeks",
            definition=(
                f"Collected weeks / weeks on asbdavani.app/racecards index ({source_note})"
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
        # Kept for audit transparency — DO NOT use as product primary
        "deprecated_mixed_month_plus_city": CoverageFraction(
            name="deprecated_mixed_month_plus_city",
            numerator=legacy_mixed_num,
            denominator=legacy_mixed_den,
            unit="mixed_cells",
            definition=(
                "DEPRECATED: (filled_months + filled_city_months) / "
                "(eligible_months + city_months_in_active_months). Double-counts structure."
            ),
        ),
    }

    remaining_problem = unresolved
    legacy = legacy_gap_penalty_proxy(remaining_problem)
    # Product primary = proven obligation (matrix formula). Grid-fill kept as companion.
    primary = metrics["proven_obligation_coverage"]

    # Persist classification tables for audit
    try:
        ART.mkdir(parents=True, exist_ok=True)
        import json

        (ART / "coverage_primary_cells_classified.json").write_text(
            json.dumps(
                {
                    "total": len(primary_cells),
                    "counts": dict(primary_class),
                    "cells": primary_cells,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (ART / "coverage_city_month_cells_classified.json").write_text(
            json.dumps(
                {
                    "total": len(city_cells),
                    "counts": dict(city_class),
                    "cells": city_cells,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "today_jalali": f"{jy_today}/{jm_today:02d}/{today.day:02d}",
        "span_jalali": f"{y_min}→{y_max}",
        "known_tracks": track_list,
        "includes_1405": {
            "in_span": y_min <= 1405 <= y_max,
            "eligible_months": [m for (y, m) in eligible_months if y == 1405],
            "primary_cells": sum(1 for c in primary_cells if c["jalali_year"] == 1405),
            "primary_class": dict(
                Counter(c["class"] for c in primary_cells if c["jalali_year"] == 1405)
            ),
        },
        "classification": {
            "primary_universe": dict(primary_class),
            "primary_universe_size": len(primary_cells),
            "month_universe": dict(month_class),
            "city_month_universe": dict(city_class),
        },
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
        "coverage_formula": (
            "CONFIRMED_RACE / (CONFIRMED_RACE + MISSING_DATA) — "
            "full year×month×city matrix is authoritative via build_coverage_matrix.py"
        ),
        "metrics": {k: v.as_dict() for k, v in metrics.items()},
        "legacy_proxy_explanation": legacy,
        "why_not_31_72": (
            "31.72% was legacy_gap_penalty_proxy with remaining_problem_gaps=1328: "
            "45 - 13.28 = 31.72. It was not calendar, heat, result, or source coverage."
        ),
        "definition_fixes": [
            "Product Coverage = proven race-obligation only (UNRESOLVED out)",
            "Full matrix year×month×city via src/coverage/matrix.py",
            "Empty alone never No-Race",
            "NO_RACE excluded from Coverage denominator (not Missing Data debt)",
        ],
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
        if pct < (gate.min_coverage_pct or 70.0):
            gate.allowed = False
        gate.current_coverage_pct = pct
        gate.notes = (
            f"primary_metric={report.get('primary_metric')}; "
            f"Coverage=CONFIRMED_RACE/(CONFIRMED_RACE+MISSING_DATA); "
            f"UNRESOLVED excluded; empty≠no-race; enrichment blocked below min"
        )
    session.flush()
    return report
