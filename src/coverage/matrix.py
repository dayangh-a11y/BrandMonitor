"""Full Coverage Matrix: Jalali year × month × city.

No enrichment. Empty cells are never assumed No-Race.
Product Coverage uses only proven race-obligation cells:

    Coverage = CONFIRMED_RACE / (CONFIRMED_RACE + MISSING_DATA)

UNRESOLVED is excluded (existence/absence not proven).
CONFIRMED_NO_RACE is proven absence and is reported separately —
it is not Missing Data debt and is not in the Coverage denominator.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

import jdatetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.coverage.models import CovMissingGap
from src.utils.jalali import today_jalali
from src.warehouse.models import WhRace, WhRaceResult

CellStatus = Literal[
    "CONFIRMED_RACE",
    "CONFIRMED_NO_RACE",
    "MISSING_DATA",
    "UNRESOLVED",
]

ART = Path("/opt/cursor/artifacts")
HISTORY_EVIDENCE = Path("/tmp/history_evidence.json")
KNOWN_BREEDS = ("تروبرد", "دوخون", "عرب", "ترکمن")


def norm_city(name: str | None) -> str | None:
    if not name:
        return None
    t = name.replace("\u200c", " ").replace("\u200d", "")
    t = re.sub(r"\s+", " ", t).strip()
    return t or None


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


def _is_future(y: int, m: int, jy_today: int, jm_today: int) -> bool:
    return (y > jy_today) or (y == jy_today and m > jm_today)


@dataclass
class MatrixCell:
    jalali_year: int
    jalali_month: int
    city: str
    status: CellStatus
    race_days: int = 0
    heats: int = 0
    results: int = 0
    breeds: list[str] = field(default_factory=list)
    source: str | None = None
    source_urls: list[str] = field(default_factory=list)
    # MISSING_DATA
    proving_source: str | None = None
    proving_dates: list[str] = field(default_factory=list)
    probable_race_days: int | None = None
    confidence_score: float | None = None
    proving_url: str | None = None
    # NO_RACE / UNRESOLVED
    evidence: str | None = None
    unresolved_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _infer_breeds(surfaces: set[str], names: set[str]) -> list[str]:
    found: set[str] = set()
    for s in surfaces:
        if s and s != "UNKNOWN" and s in KNOWN_BREEDS:
            found.add(s)
    blob = " ".join(names)
    for b in KNOWN_BREEDS:
        if b in blob:
            found.add(b)
    return sorted(found)


def _load_history_missing(wh_heats: dict[tuple[int, int, str], int]) -> dict[tuple[int, int, str], dict]:
    """City-months proven by horse-history but still empty in WH → MISSING_DATA."""
    out: dict[tuple[int, int, str], dict] = {}
    if not HISTORY_EVIDENCE.exists():
        return out
    try:
        data = json.loads(HISTORY_EVIDENCE.read_text(encoding="utf-8"))
    except Exception:
        return out
    cells = data.get("cells") or {}
    for key, rows in cells.items():
        parts = str(key).split("|")
        if len(parts) != 3:
            continue
        try:
            y, m = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        city = norm_city(parts[2])
        if not city or city == "*":
            continue
        if wh_heats.get((y, m, city), 0) > 0:
            continue
        dates = sorted({r.get("date") for r in rows if r.get("date")})
        urls = sorted({r.get("url") for r in rows if r.get("url")})
        out[(y, m, city)] = {
            "proving_source": "asbdavani_horse_history",
            "proving_dates": dates,
            "probable_race_days": len(dates),
            "confidence_score": 0.92,
            "proving_url": urls[0] if urls else None,
            "source_urls": urls[:20],
            "heats_evidence": len(rows),
        }
    return out


def _load_csv_missing(wh_heats: dict[tuple[int, int, str], int]) -> dict[tuple[int, int, str], dict]:
    """Open MISSING_DATA proofs from classification CSVs (city still empty)."""
    out: dict[tuple[int, int, str], dict] = {}
    paths = [
        ART / "needs_investigation_resolution.csv",
        ART / "missing_coverage_confirmed_missing_data.csv",
    ]
    for path in paths:
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                result = row.get("result") or row.get("final_status") or ""
                if "missing_data" not in result and result != "confirmed_missing_data":
                    # phase-A file uses final_status resolved_filled after extract
                    if result == "resolved_filled":
                        continue
                    if "missing" not in result.lower():
                        continue
                try:
                    y = int(row["jalali_year"])
                    m = int(row["jalali_month"])
                except (KeyError, ValueError):
                    continue
                cities: list[str] = []
                city_raw = norm_city(row.get("city"))
                if city_raw and city_raw not in ("nationwide", "*"):
                    cities.append(city_raw)
                ev_raw = row.get("evidence") or ""
                try:
                    ev = json.loads(ev_raw) if ev_raw.startswith("{") else {}
                except json.JSONDecodeError:
                    ev = {}
                for c in ev.get("cities") or []:
                    cn = norm_city(c)
                    if cn and cn not in cities:
                        cities.append(cn)
                conf = row.get("confidence") or row.get("confidence_score")
                try:
                    conf_f = float(conf) if conf not in (None, "") else 0.9
                except ValueError:
                    conf_f = 0.9
                try:
                    probable = int(row.get("race_days") or 0) or None
                except ValueError:
                    probable = None
                url = row.get("source_url") or None
                src = row.get("source_checked") or row.get("source") or "external_proof"
                for city in cities:
                    if wh_heats.get((y, m, city), 0) > 0:
                        continue
                    out[(y, m, city)] = {
                        "proving_source": src,
                        "proving_dates": list(ev.get("dates") or []),
                        "probable_race_days": probable,
                        "confidence_score": conf_f,
                        "proving_url": url,
                        "source_urls": [url] if url else [],
                    }
    return out


def build_coverage_matrix(session: Session) -> dict[str, Any]:
    races = list(session.scalars(select(WhRace).where(WhRace.race_date.is_not(None))).all())
    results = list(session.scalars(select(WhRaceResult)).all())
    gaps = list(session.scalars(select(CovMissingGap)).all())

    results_by_race: dict[int, int] = defaultdict(int)
    for res in results:
        if res.race_id is not None:
            results_by_race[int(res.race_id)] += 1

    # Aggregate WH by (jy, jm, city)
    cell_races: dict[tuple[int, int, str], list[WhRace]] = defaultdict(list)
    tracks: set[str] = set()
    years: set[int] = set()

    for r in races:
        g = _gdate(r.race_date)
        if g is None:
            continue
        jd = jdatetime.date.fromgregorian(date=g)
        city = norm_city(r.track)
        if not city:
            continue
        tracks.add(city)
        years.add(jd.year)
        cell_races[(jd.year, jd.month, city)].append(r)

    for g in gaps:
        cn = norm_city(g.track)
        if cn:
            tracks.add(cn)
        if g.jalali_year is not None:
            years.add(int(g.jalali_year))

    track_list = sorted(tracks)
    if not years:
        return {"error": "no_years", "cells": []}

    y_min, y_max = min(years), max(years)
    today = today_jalali()
    jy_today, jm_today = today.year, today.month

    wh_heats = {k: len(v) for k, v in cell_races.items()}

    gap_month_no_race: set[tuple[int, int]] = set()
    gap_city_no_race: set[tuple[int, int, str]] = set()
    gap_city_md: dict[tuple[int, int, str], CovMissingGap] = {}
    gap_evidence: dict[tuple[int, int] | tuple[int, int, str], str] = {}

    for g in gaps:
        if g.jalali_year is None or g.jalali_month is None:
            continue
        y, m = int(g.jalali_year), int(g.jalali_month)
        if g.status == "confirmed_no_race":
            if g.scope_type == "month" or not g.track:
                gap_month_no_race.add((y, m))
            city = norm_city(g.track)
            if city:
                gap_city_no_race.add((y, m, city))
            gap_evidence[(y, m) if not g.track else (y, m, norm_city(g.track) or "")] = (
                g.evidence_json or g.notes or "confirmed_no_race"
            )
        if g.status == "confirmed_missing_data":
            city = norm_city(g.track)
            if city:
                gap_city_md[(y, m, city)] = g

    hist_md = _load_history_missing(wh_heats)
    csv_md = _load_csv_missing(wh_heats)
    # history wins on conflict (richer URLs); then csv; then open gap
    missing_proofs: dict[tuple[int, int, str], dict] = {}
    missing_proofs.update(csv_md)
    missing_proofs.update(hist_md)
    for key, g in gap_city_md.items():
        if key in missing_proofs:
            continue
        if wh_heats.get(key, 0) > 0:
            continue
        try:
            ev = json.loads(g.evidence_json) if g.evidence_json else {}
        except json.JSONDecodeError:
            ev = {}
        missing_proofs[key] = {
            "proving_source": ev.get("source") or "gap_ledger",
            "proving_dates": list(ev.get("dates") or []),
            "probable_race_days": ev.get("race_days_evidence"),
            "confidence_score": float(ev.get("confidence") or 0.85),
            "proving_url": ev.get("source_url"),
            "source_urls": list(ev.get("urls") or []),
        }

    cells: list[MatrixCell] = []
    for y in range(y_min, y_max + 1):
        for m in range(1, 13):
            for city in track_list:
                key = (y, m, city)
                race_list = cell_races.get(key, [])
                if race_list:
                    race_days = len({(_gdate(r.race_date), city) for r in race_list})
                    heats = len(race_list)
                    n_results = sum(results_by_race.get(int(r.id), 0) for r in race_list)
                    surfaces = {r.surface for r in race_list if r.surface}
                    names = {r.name for r in race_list if r.name}
                    sources = sorted({r.source for r in race_list if r.source})
                    urls = sorted({r.source_url for r in race_list if r.source_url})
                    cells.append(
                        MatrixCell(
                            jalali_year=y,
                            jalali_month=m,
                            city=city,
                            status="CONFIRMED_RACE",
                            race_days=race_days,
                            heats=heats,
                            results=n_results,
                            breeds=_infer_breeds(surfaces, names),
                            source=",".join(sources) if sources else None,
                            source_urls=urls[:30],
                            evidence=f"heats_in_db={heats}",
                        )
                    )
                    continue

                if _is_future(y, m, jy_today, jm_today) or (y, m) in gap_month_no_race or key in gap_city_no_race:
                    ev = gap_evidence.get(key) or gap_evidence.get((y, m))
                    if _is_future(y, m, jy_today, jm_today):
                        reason = (
                            f"future_jalali_month after today {jy_today}/{jm_today:02d}; "
                            "no race can have occurred yet"
                        )
                    else:
                        reason = "gap_ledger confirmed_no_race"
                    cells.append(
                        MatrixCell(
                            jalali_year=y,
                            jalali_month=m,
                            city=city,
                            status="CONFIRMED_NO_RACE",
                            evidence=ev or reason,
                        )
                    )
                    continue

                if key in missing_proofs:
                    proof = missing_proofs[key]
                    cells.append(
                        MatrixCell(
                            jalali_year=y,
                            jalali_month=m,
                            city=city,
                            status="MISSING_DATA",
                            proving_source=proof.get("proving_source"),
                            proving_dates=list(proof.get("proving_dates") or []),
                            probable_race_days=proof.get("probable_race_days"),
                            confidence_score=proof.get("confidence_score"),
                            proving_url=proof.get("proving_url"),
                            source_urls=list(proof.get("source_urls") or [])[:20],
                            source=proof.get("proving_source"),
                            evidence=(
                                "External proof that races occurred; warehouse cell still empty. "
                                "Empty≠No-Race."
                            ),
                        )
                    )
                    continue

                cells.append(
                    MatrixCell(
                        jalali_year=y,
                        jalali_month=m,
                        city=city,
                        status="UNRESOLVED",
                        unresolved_reason=(
                            "Empty warehouse cell with no external proof of racing "
                            "and no proof of absence; empty≠no-race and empty≠missing_data"
                        ),
                        evidence="empty_no_proof",
                    )
                )

    status_counts = Counter(c.status for c in cells)
    confirmed_race = status_counts["CONFIRMED_RACE"]
    missing_data = status_counts["MISSING_DATA"]
    confirmed_no_race = status_counts["CONFIRMED_NO_RACE"]
    unresolved = status_counts["UNRESOLVED"]

    coverage_num = confirmed_race
    coverage_den = confirmed_race + missing_data
    coverage_pct = (
        round(100.0 * coverage_num / coverage_den, 4) if coverage_den > 0 else None
    )

    # Annual summary
    annual: list[dict[str, Any]] = []
    for y in range(y_min, y_max + 1):
        year_cells = [c for c in cells if c.jalali_year == y]
        months_with_race = sorted(
            {c.jalali_month for c in year_cells if c.status == "CONFIRMED_RACE"}
        )
        cities_with_race = sorted(
            {c.city for c in year_cells if c.status == "CONFIRMED_RACE"}
        )
        annual.append(
            {
                "year": y,
                "months_with_race": months_with_race,
                "months_with_race_count": len(months_with_race),
                "race_days": sum(c.race_days for c in year_cells),
                "heats": sum(c.heats for c in year_cells),
                "results": sum(c.results for c in year_cells),
                "cities": cities_with_race,
                "cities_count": len(cities_with_race),
                "missing_data": sum(1 for c in year_cells if c.status == "MISSING_DATA"),
                "unresolved": sum(1 for c in year_cells if c.status == "UNRESOLVED"),
                "confirmed_race": sum(1 for c in year_cells if c.status == "CONFIRMED_RACE"),
                "confirmed_no_race": sum(
                    1 for c in year_cells if c.status == "CONFIRMED_NO_RACE"
                ),
            }
        )

    monthly = [
        {
            "month": c.jalali_month,
            "year": c.jalali_year,
            "city": c.city,
            "status": c.status,
            "race_days": c.race_days,
            "heats": c.heats,
            "results": c.results,
            "source": c.source
            or c.proving_source
            or (
                "calendar_future"
                if c.status == "CONFIRMED_NO_RACE"
                else ("none" if c.status == "UNRESOLVED" else None)
            ),
        }
        for c in cells
    ]

    formula = {
        "name": "Coverage",
        "formula": "CONFIRMED_RACE / (CONFIRMED_RACE + MISSING_DATA)",
        "numerator": coverage_num,
        "denominator": coverage_den,
        "pct": coverage_pct,
        "display": (
            f"{coverage_num}/{coverage_den} = {coverage_pct:.2f}%"
            if coverage_pct is not None
            else "n/a"
        ),
        "includes": [
            "CONFIRMED_RACE — race proven by warehouse heats",
            "MISSING_DATA — race proven externally, warehouse empty",
        ],
        "excludes": [
            "UNRESOLVED — existence/absence not proven (empty≠no-race)",
            "CONFIRMED_NO_RACE — proven absence; not Missing Data debt",
        ],
        "rule": "Never treat empty alone as No-Race. Coverage only on proven race-obligation cells.",
        "companion_proven_resolution": {
            "formula": "(CONFIRMED_RACE + CONFIRMED_NO_RACE) / (RACE + NO_RACE + MISSING_DATA)",
            "numerator": confirmed_race + confirmed_no_race,
            "denominator": confirmed_race + confirmed_no_race + missing_data,
            "note": "Share of cells whose race presence/absence is proven and classified",
        },
    }

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "today_jalali": f"{jy_today}/{jm_today:02d}/{today.day:02d}",
        "span_jalali": f"{y_min}→{y_max}",
        "cities": track_list,
        "structure": "jalali_year × jalali_month × city",
        "total_cells": len(cells),
        "status_counts": {
            "CONFIRMED_RACE": confirmed_race,
            "CONFIRMED_NO_RACE": confirmed_no_race,
            "MISSING_DATA": missing_data,
            "UNRESOLVED": unresolved,
        },
        "coverage": formula,
        "annual": annual,
        "monthly": monthly,
        "cells": [c.as_dict() for c in cells],
        "enrichment_blocked": True,
        "notes": [
            "No enrichment (pedigree/weather/ranking/prediction) until coverage matrix work completes.",
            "No new extract/merge in this matrix build — read-only from WH + gap ledger + prior evidence.",
        ],
    }


def write_matrix_artifacts(report: dict[str, Any], art: Path | None = None) -> dict[str, str]:
    art = art or ART
    art.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}

    full_path = art / "coverage_matrix_full.json"
    # Full JSON can be large; write compact cells separately if needed
    full_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    paths["full_json"] = str(full_path)

    # Cells CSV
    cells_csv = art / "coverage_matrix_cells.csv"
    cell_fields = [
        "jalali_year",
        "jalali_month",
        "city",
        "status",
        "race_days",
        "heats",
        "results",
        "breeds",
        "source",
        "source_urls",
        "proving_source",
        "proving_dates",
        "probable_race_days",
        "confidence_score",
        "proving_url",
        "evidence",
        "unresolved_reason",
    ]
    with cells_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cell_fields, extrasaction="ignore")
        w.writeheader()
        for c in report["cells"]:
            row = dict(c)
            row["breeds"] = "|".join(c.get("breeds") or [])
            row["source_urls"] = "|".join(c.get("source_urls") or [])
            row["proving_dates"] = "|".join(c.get("proving_dates") or [])
            w.writerow(row)
    paths["cells_csv"] = str(cells_csv)

    annual_csv = art / "coverage_matrix_annual.csv"
    with annual_csv.open("w", encoding="utf-8", newline="") as f:
        fields = [
            "year",
            "months_with_race_count",
            "months_with_race",
            "race_days",
            "heats",
            "results",
            "cities_count",
            "cities",
            "missing_data",
            "unresolved",
            "confirmed_race",
            "confirmed_no_race",
        ]
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for a in report["annual"]:
            row = dict(a)
            row["months_with_race"] = "|".join(str(x) for x in a["months_with_race"])
            row["cities"] = "|".join(a["cities"])
            w.writerow(row)
    paths["annual_csv"] = str(annual_csv)

    monthly_csv = art / "coverage_matrix_monthly.csv"
    with monthly_csv.open("w", encoding="utf-8", newline="") as f:
        fields = [
            "month",
            "year",
            "city",
            "status",
            "race_days",
            "heats",
            "results",
            "source",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in report["monthly"]:
            w.writerow(row)
    paths["monthly_csv"] = str(monthly_csv)

    # Summary markdown
    sc = report["status_counts"]
    cov = report["coverage"]
    md_lines = [
        "# Coverage Matrix",
        "",
        f"Generated: `{report['generated_at_utc']}`",
        f"Today (Jalali): **{report['today_jalali']}**",
        f"Span: **{report['span_jalali']}**",
        f"Cities ({len(report['cities'])}): {', '.join(report['cities'])}",
        f"Structure: `{report['structure']}`",
        f"Total cells: **{report['total_cells']}**",
        "",
        "## Coverage formula (product)",
        "",
        "```text",
        "Coverage = CONFIRMED_RACE / (CONFIRMED_RACE + MISSING_DATA)",
        f"         = {cov['display']}",
        "```",
        "",
        "- Denominator = cells where a race is **proven to have occurred** (captured or still missing).",
        "- **UNRESOLVED** excluded (empty alone is not proof).",
        "- **CONFIRMED_NO_RACE** excluded from Coverage debt (proven absence, not missing data).",
        "",
        "## Cell status counts",
        "",
        "| Status | Cells |",
        "|---|---:|",
        f"| CONFIRMED_RACE | {sc['CONFIRMED_RACE']} |",
        f"| CONFIRMED_NO_RACE | {sc['CONFIRMED_NO_RACE']} |",
        f"| MISSING_DATA | {sc['MISSING_DATA']} |",
        f"| UNRESOLVED | {sc['UNRESOLVED']} |",
        f"| **Total** | **{report['total_cells']}** |",
        "",
        "## Annual summary",
        "",
        "| سال | ماه‌های دارای مسابقه | Race Day | Heat | Result | شهرها | Missing Data | Unresolved |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for a in report["annual"]:
        md_lines.append(
            f"| {a['year']} | {a['months_with_race_count']} | {a['race_days']} | "
            f"{a['heats']} | {a['results']} | {a['cities_count']} | "
            f"{a['missing_data']} | {a['unresolved']} |"
        )

    md_lines += [
        "",
        "## Monthly table (excerpt — full CSV on disk)",
        "",
        "| ماه | سال | شهر | وضعیت | Race Day | Heat | Result | Source |",
        "|---:|---:|---|---|---:|---:|---:|---|",
    ]
    # Show CONFIRMED_RACE + MISSING_DATA + NO_RACE in excerpt; sample UNRESOLVED
    excerpt = [
        c
        for c in report["monthly"]
        if c["status"] in ("CONFIRMED_RACE", "MISSING_DATA", "CONFIRMED_NO_RACE")
    ]
    for row in excerpt[:80]:
        md_lines.append(
            f"| {row['month']} | {row['year']} | {row['city']} | {row['status']} | "
            f"{row['race_days']} | {row['heats']} | {row['results']} | {row['source']} |"
        )
    if len(excerpt) > 80:
        md_lines.append(f"| … | … | … | ({len(excerpt) - 80} more non-UNRESOLVED rows in CSV) | … | … | … | … |")

    md_path = art / "coverage_matrix.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    paths["markdown"] = str(md_path)

    # Compact summary JSON (no full cells)
    summary = {k: v for k, v in report.items() if k not in ("cells", "monthly")}
    summary["monthly_rows"] = len(report["monthly"])
    summary["artifact_paths"] = paths
    summary_path = art / "coverage_matrix_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["summary_json"] = str(summary_path)
    return paths
