"""National Ranking and Fair Comparison Mode for Iran Post-aware comparisons."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from postal.iran_post.geo import (
    company_geo_sets,
    coverage_percentage,
    normalize_city,
)
from postal.iran_post.profile import load_official_profile
from postal.metric_confidence import metric_confidence_bundle

DEFAULT_DB = os.getenv("POSTAL_DB_PATH", "data/postal_intelligence.db")
TARGET_PROVINCES = 31
TARGET_CITIES = 100


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class NationalRanking:
    mode: str
    generated_at: str
    rows: list[dict[str, Any]]
    warnings: list[str]
    display: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "generated_at": self.generated_at,
            "rows": self.rows,
            "warnings": self.warnings,
            "display": self.display,
        }


@dataclass
class FairComparison:
    mode: str
    generated_at: str
    selected_slugs: list[str]
    common_cities: list[str]
    rows: list[dict[str, Any]]
    warnings: list[str]
    display: dict[str, Any]
    eligible: bool
    message: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "generated_at": self.generated_at,
            "selected_slugs": self.selected_slugs,
            "common_cities": self.common_cities,
            "rows": self.rows,
            "warnings": self.warnings,
            "display": self.display,
            "eligible": self.eligible,
            "message": self.message,
        }


def compare(
    *,
    mode: str = "national",
    slugs: Sequence[str] | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    mode_n = (mode or "national").strip().lower()
    if mode_n in {"national", "national_ranking", "all"}:
        return national_ranking(slugs=slugs, db_path=db_path).as_dict()
    if mode_n in {"fair", "fair_comparison", "intersection"}:
        return fair_comparison(slugs=slugs, db_path=db_path).as_dict()
    raise ValueError("mode must be 'national' or 'fair'")


def _connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or DEFAULT_DB
    if not Path(path).exists():
        raise FileNotFoundError(
            f"Postal DB not found: {path}. Run scripts/build_postal_intelligence.py first."
        )
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _load_companies(conn: sqlite3.Connection, slugs: Sequence[str] | None) -> list[dict[str, Any]]:
    rows = [dict(r) for r in conn.execute("SELECT * FROM pi_companies ORDER BY name")]
    if slugs:
        wanted = {s.strip().lower() for s in slugs}
        rows = [r for r in rows if r["slug"].lower() in wanted]
    return rows


def _latest_score(conn: sqlite3.Connection, company_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT score, dimensions_json, calculated_at, algorithm_version
        FROM pi_company_scores
        WHERE company_id=?
        ORDER BY id DESC LIMIT 1
        """,
        (company_id,),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["dimensions"] = json.loads(d.pop("dimensions_json") or "{}")
    return d


def _review_stats(conn: sqlite3.Connection, company_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT COUNT(*) n, AVG(rating) a FROM pi_reviews WHERE company_id=?",
        (company_id,),
    ).fetchone()
    return {
        "review_count": int(row["n"] or 0),
        "avg_rating": round(float(row["a"] or 0), 3),
    }


def _company_row(
    conn: sqlite3.Connection,
    company: dict[str, Any],
    *,
    iran_post_profile: dict[str, Any],
    city_filter: set[str] | None = None,
) -> dict[str, Any]:
    cid = int(company["id"])
    geo = company_geo_sets(conn, cid)
    stats = _review_stats(conn, cid)
    score = _latest_score(conn, cid)
    is_post = company["slug"].lower() in {"post", "iran_post", "iran-post"}

    # Optional city-filtered branch/review counts for fair mode
    if city_filter is not None:
        branch_ids = []
        for b in conn.execute(
            "SELECT id, city FROM pi_branches WHERE company_id=?", (cid,)
        ):
            if normalize_city(b["city"]) in city_filter:
                branch_ids.append(int(b["id"]))
        branch_count = len(branch_ids)
        if branch_ids:
            placeholders = ",".join("?" for _ in branch_ids)
            rev = conn.execute(
                f"SELECT COUNT(*) n, AVG(rating) a FROM pi_reviews "
                f"WHERE company_id=? AND branch_id IN ({placeholders})",
                (cid, *branch_ids),
            ).fetchone()
            review_count = int(rev["n"] or 0)
            avg_rating = round(float(rev["a"] or 0), 3)
        else:
            review_count = 0
            avg_rating = 0.0
        province_count = len(
            {
                normalize_city(p)  # unused normalize; keep provinces from filtered branches
                for p in []
            }
        )
        # recompute provinces from filtered branches
        provs = set()
        cities = set()
        for b in conn.execute(
            "SELECT city, province FROM pi_branches WHERE company_id=?", (cid,)
        ):
            if normalize_city(b["city"]) in city_filter:
                cities.add(normalize_city(b["city"]))
                if b["province"]:
                    provs.add(str(b["province"]))
        province_count = len(provs)
        city_count = len(cities)
    else:
        branch_count = geo["branch_count"]
        review_count = stats["review_count"]
        avg_rating = stats["avg_rating"]
        province_count = len(geo["provinces"])
        city_count = len(geo["cities"])

    # Official claimed coverage for Post vs observed for others
    coverage_official = None
    if is_post:
        cov = iran_post_profile.get("service_coverage") or {}
        coverage_official = {
            "provinces_official": cov.get("provinces_official"),
            "cities_official": cov.get("cities_covered_official"),
            "branches_official": cov.get("branch_count_official"),
        }

    conf = metric_confidence_bundle(
        review_count=review_count,
        branch_count=branch_count,
        city_count=city_count,
        province_count=province_count,
        official_completeness_ratio=1.0 if is_post else 0.5,
        official_reachable=True,
    )

    coverage_pct_provinces = coverage_percentage(province_count, TARGET_PROVINCES)
    # For Post national claims, also expose official coverage %
    if is_post and coverage_official and coverage_official.get("provinces_official"):
        official_cov_pct = coverage_percentage(
            int(coverage_official["provinces_official"] or 0), TARGET_PROVINCES
        )
    else:
        official_cov_pct = None

    return {
        "slug": company["slug"],
        "company": "Iran Post" if is_post else company["name"],
        "name_fa": company.get("name_fa") or "",
        "role": "national_postal_operator" if is_post else "private_carrier",
        "score": None if score is None else float(score["score"]),
        "algorithm_version": None if score is None else score.get("algorithm_version"),
        "coverage_percentage": coverage_pct_provinces,
        "coverage_percentage_official": official_cov_pct,
        "number_of_branches": branch_count,
        "number_of_reviews": review_count,
        "confidence_score": conf["overall_dataset_confidence"],
        "city_count_observed": city_count,
        "province_count_observed": province_count,
        "avg_rating": avg_rating,
        "official_coverage": coverage_official,
        "is_iran_post": is_post,
    }


def _coverage_inequality_warnings(rows: list[dict[str, Any]], gap_pct: float) -> list[str]:
    warnings: list[str] = []
    if len(rows) < 2:
        return warnings
    coverages = [float(r.get("coverage_percentage") or 0) for r in rows]
    lo, hi = min(coverages), max(coverages)
    gap = hi - lo
    if gap >= gap_pct:
        warnings.append(
            f"Unequal geographic coverage detected (observed province coverage "
            f"gap {gap:.1f} percentage points). National Ranking can mislead when "
            f"networks do not overlap. Prefer Fair Comparison Mode for route-level decisions."
        )
    if any(r.get("is_iran_post") for r in rows):
        warnings.append(
            "Iran Post is the national postal operator, not a regular private carrier. "
            "Its official claimed network scale differs from Maps-observed private footprints. "
            "Do not treat official branch counts and observed private branch counts as equivalent."
        )
        post = next(r for r in rows if r.get("is_iran_post"))
        others = [r for r in rows if not r.get("is_iran_post")]
        if others:
            max_other = max(int(r["number_of_branches"]) for r in others)
            if int(post.get("official_coverage", {}).get("branches_official") or 0) > max_other * 5:
                warnings.append(
                    "Iran Post official branch_count is an order of magnitude larger than "
                    "observed private networks in this warehouse — unequal coverage warning."
                )
    return warnings


def national_ranking(
    *,
    slugs: Sequence[str] | None = None,
    db_path: str | None = None,
) -> NationalRanking:
    profile = load_official_profile()
    gap = float(
        (profile.get("comparison_policy") or {}).get(
            "fair_mode_required_when_coverage_gap_pct", 25
        )
    )
    conn = _connect(db_path)
    try:
        companies = _load_companies(conn, slugs)
        rows = [
            _company_row(conn, c, iran_post_profile=profile, city_filter=None)
            for c in companies
        ]
        rows.sort(key=lambda r: float(r["score"] or 0), reverse=True)
        for i, row in enumerate(rows, 1):
            row["national_rank"] = i
        warnings = _coverage_inequality_warnings(rows, gap)
        display = {
            "columns": [
                "national_rank",
                "company",
                "role",
                "score",
                "coverage_percentage",
                "number_of_branches",
                "number_of_reviews",
                "confidence_score",
            ],
            "rows": [
                [
                    r["national_rank"],
                    r["company"],
                    r["role"],
                    r["score"],
                    r["coverage_percentage"],
                    r["number_of_branches"],
                    r["number_of_reviews"],
                    r["confidence_score"],
                ]
                for r in rows
            ],
        }
        return NationalRanking(
            mode="national_ranking",
            generated_at=utcnow(),
            rows=rows,
            warnings=warnings,
            display=display,
        )
    finally:
        conn.close()


def fair_comparison(
    *,
    slugs: Sequence[str] | None = None,
    db_path: str | None = None,
) -> FairComparison:
    """Compare only cities where ALL selected companies have observed branches."""
    profile = load_official_profile()
    conn = _connect(db_path)
    try:
        companies = _load_companies(conn, slugs)
        if len(companies) < 2:
            return FairComparison(
                mode="fair_comparison",
                generated_at=utcnow(),
                selected_slugs=[c["slug"] for c in companies],
                common_cities=[],
                rows=[],
                warnings=["Fair Comparison Mode requires at least two companies."],
                display={"columns": [], "rows": []},
                eligible=False,
                message="I don't have enough data.",
            )

        geo_by_id = {int(c["id"]): company_geo_sets(conn, int(c["id"])) for c in companies}
        city_sets = [geo_by_id[int(c["id"])]["cities"] for c in companies]
        common = set.intersection(*city_sets) if city_sets else set()
        common_sorted = sorted(common)

        warnings: list[str] = []
        if any(c["slug"].lower() == "post" for c in companies):
            warnings.append(
                "Iran Post is included as national_postal_operator. Fair mode uses "
                "Maps-observed post-office cities only (not the full official 9000-branch claim)."
            )

        if not common_sorted:
            # Explicit unequal coverage — do not silently compare
            warnings.append(
                "No common observed cities across all selected companies. "
                "Refusing Fair Comparison rather than inventing overlap."
            )
            # still show per-company coverage diagnostics
            diag = [
                _company_row(conn, c, iran_post_profile=profile, city_filter=None)
                for c in companies
            ]
            gap = float(
                (profile.get("comparison_policy") or {}).get(
                    "fair_mode_required_when_coverage_gap_pct", 25
                )
            )
            warnings.extend(_coverage_inequality_warnings(diag, gap))
            return FairComparison(
                mode="fair_comparison",
                generated_at=utcnow(),
                selected_slugs=[c["slug"] for c in companies],
                common_cities=[],
                rows=diag,
                warnings=warnings,
                display={
                    "columns": [
                        "company",
                        "role",
                        "coverage_percentage",
                        "number_of_branches",
                        "number_of_reviews",
                        "confidence_score",
                    ],
                    "rows": [
                        [
                            r["company"],
                            r["role"],
                            r["coverage_percentage"],
                            r["number_of_branches"],
                            r["number_of_reviews"],
                            r["confidence_score"],
                        ]
                        for r in diag
                    ],
                },
                eligible=False,
                message=(
                    "I don't have enough data. Selected companies do not share "
                    "observed operating cities in this warehouse."
                ),
            )

        city_filter = set(common_sorted)
        rows = [
            _company_row(conn, c, iran_post_profile=profile, city_filter=city_filter)
            for c in companies
        ]
        rows.sort(key=lambda r: float(r["score"] or 0), reverse=True)
        for i, row in enumerate(rows, 1):
            row["fair_rank"] = i
            row["fair_city_universe"] = common_sorted

        # In fair mode, coverage inequality on the filtered set should be small;
        # still warn if review samples are tiny.
        for r in rows:
            if int(r["number_of_reviews"]) < 10:
                warnings.append(
                    f"{r['company']} has fewer than 10 reviews inside the fair-city set "
                    f"({r['number_of_reviews']}) — interpret cautiously."
                )

        display = {
            "columns": [
                "fair_rank",
                "company",
                "role",
                "score",
                "coverage_percentage",
                "number_of_branches",
                "number_of_reviews",
                "confidence_score",
            ],
            "rows": [
                [
                    r["fair_rank"],
                    r["company"],
                    r["role"],
                    r["score"],
                    r["coverage_percentage"],
                    r["number_of_branches"],
                    r["number_of_reviews"],
                    r["confidence_score"],
                ]
                for r in rows
            ],
            "common_cities": common_sorted,
        }
        return FairComparison(
            mode="fair_comparison",
            generated_at=utcnow(),
            selected_slugs=[c["slug"] for c in companies],
            common_cities=common_sorted,
            rows=rows,
            warnings=warnings,
            display=display,
            eligible=True,
            message=None,
        )
    finally:
        conn.close()
