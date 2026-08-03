"""Iran Post dedicated module — national operator, not a private carrier adapter."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Sequence

from postal.iran_post.compare import FairComparison, NationalRanking, compare, fair_comparison, national_ranking
from postal.iran_post.maps_reviews import collect_post_office_reviews
from postal.iran_post.profile import load_official_profile, profile_public_view

DEFAULT_DB = os.getenv("POSTAL_DB_PATH", "data/postal_intelligence.db")


class IranPostModule:
    """
    Collects and maintains official Iran Post reference data plus observed
    Google Maps post-office reviews from the warehouse.

    Intentionally separate from private-carrier pricing adapters. Comparisons
    must use National Ranking or Fair Comparison Mode and always surface
    coverage / branches / reviews / confidence with unequal-coverage warnings.
    """

    def __init__(self, db_path: str | None = None, profile_path: str | None = None) -> None:
        self.db_path = db_path or DEFAULT_DB
        self.profile_path = profile_path
        self._profile = load_official_profile(profile_path)

    def _connect(self) -> sqlite3.Connection:
        path = Path(self.db_path)
        if not path.exists():
            raise FileNotFoundError(
                f"Postal DB not found: {path}. Run scripts/build_postal_intelligence.py first."
            )
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        return conn

    def _post_company_id(self, conn: sqlite3.Connection) -> int:
        row = conn.execute(
            "SELECT id FROM pi_companies WHERE lower(slug) IN ('post','iran_post','iran-post') LIMIT 1"
        ).fetchone()
        if not row:
            raise LookupError("Iran Post company (slug=post) not found in pi_companies")
        return int(row["id"])

    def official_profile(self) -> dict[str, Any]:
        return profile_public_view(self._profile)

    def catalog(self) -> dict[str, Any]:
        """What this dedicated module maintains (not a regular carrier pack)."""
        p = self.official_profile()
        return {
            "module": "iran_post",
            "role": "national_postal_operator",
            "not_a_regular_carrier": True,
            "treat_as_regular_carrier": False,
            "maintains": [
                "official_services",
                "official_pricing",
                "official_delivery_estimates",
                "branch_directory",
                "service_coverage",
                "weight_and_size_limits",
                "insurance_rules",
                "tracking_information_public",
                "working_hours",
                "google_maps_reviews_post_offices",
            ],
            "comparison_modes": [
                {
                    "id": "national_ranking",
                    "description": "Compare all companies using all available data (national view).",
                },
                {
                    "id": "fair_comparison",
                    "description": "Compare only cities/routes where all selected companies operate.",
                },
            ],
            "display_metrics": [
                "coverage_percentage",
                "number_of_branches",
                "number_of_reviews",
                "confidence_score",
            ],
            "coverage_warning_policy": (
                "Never compare companies with unequal geographic coverage without warning the user."
            ),
            "website": p.get("website"),
            "tracking_public_url": (p.get("tracking") or {}).get("public_url"),
            "services_count": len(p.get("official_services") or []),
            "pricing_note": (p.get("official_pricing") or {}).get("notes"),
            "tracking_public_only": bool((p.get("tracking") or {}).get("public_only", True)),
        }

    def maps_reviews(self, *, limit: int = 200) -> dict[str, Any]:
        conn = self._connect()
        try:
            cid = self._post_company_id(conn)
            return collect_post_office_reviews(conn, company_id=cid, limit=limit)
        finally:
            conn.close()

    def branch_directory(self) -> list[dict[str, Any]]:
        payload = self.maps_reviews(limit=1)
        return list(payload.get("post_offices_observed") or [])

    def snapshot(self) -> dict[str, Any]:
        profile = self.official_profile()
        maps = self.maps_reviews()
        coverage = profile.get("service_coverage") or {}
        warnings: list[str] = [
            str((self._profile.get("comparison_policy") or {}).get("national_ranking_warning") or "").strip()
        ]
        warnings = [w for w in warnings if w]
        observed = int(maps.get("post_office_count_observed") or 0)
        official_branches = int(coverage.get("branch_count_official") or 0)
        if official_branches and observed < official_branches * 0.05:
            warnings.append(
                "Observed Google Maps post-office sample is far smaller than the official "
                f"~{official_branches} branch claim. Use Fair Comparison for peer routes; "
                "National Ranking for country-level view."
            )
        return {
            "module": "iran_post",
            "role": "national_postal_operator",
            "not_a_regular_carrier": True,
            "official_profile": profile,
            "maps_reviews": {
                "review_count": maps.get("review_count"),
                "avg_rating": maps.get("avg_rating"),
                "sentiments": maps.get("sentiments"),
                "complaints": maps.get("complaints"),
                "post_office_count_observed": maps.get("post_office_count_observed"),
                "source_policy": maps.get("source_policy"),
                "recent_reviews": maps.get("recent_reviews"),
            },
            "branch_directory_observed": maps.get("post_offices_observed"),
            "display": {
                "coverage_percentage_official": round(
                    100.0
                    * min(int(coverage.get("provinces_official") or 0), 31)
                    / 31.0,
                    2,
                )
                if coverage.get("provinces_official")
                else None,
                "number_of_branches_official": coverage.get("branch_count_official"),
                "number_of_branches_observed": observed,
                "number_of_reviews": maps.get("review_count"),
                "confidence_note": (
                    "Official fields are curated_public; Maps reviews are warehouse-observed only."
                ),
            },
            "warnings": warnings,
        }

    def national_ranking(self, slugs: Sequence[str] | None = None) -> NationalRanking:
        return national_ranking(slugs=slugs, db_path=self.db_path)

    def fair_comparison(self, slugs: Sequence[str] | None = None) -> FairComparison:
        return fair_comparison(slugs=slugs, db_path=self.db_path)

    def compare(self, *, mode: str = "national", slugs: Sequence[str] | None = None) -> dict[str, Any]:
        return compare(mode=mode, slugs=slugs, db_path=self.db_path)

    def export_bundle(self) -> dict[str, Any]:
        """Full export for docs/API persistence."""
        national = self.national_ranking().as_dict()
        # Default fair set: post + top private peers present in warehouse
        fair_slugs = ["post", "tipax", "chapar", "mahex"]
        fair = self.fair_comparison(slugs=fair_slugs).as_dict()
        return {
            "catalog": self.catalog(),
            "snapshot": self.snapshot(),
            "national_ranking": national,
            "fair_comparison_default": fair,
        }
