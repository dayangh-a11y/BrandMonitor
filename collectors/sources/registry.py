from __future__ import annotations

from collectors.company_config import CompanySpec
from collectors.sources.base import BranchReviewSource


def build_source(
    source_id: str,
    *,
    headless: bool = True,
    max_branches: int | None = None,
    max_reviews_per_branch: int | None = None,
) -> BranchReviewSource:
    """
    Factory for crawl sources.

    Additional sources (Snapp Map, Balad, company websites) can register here
    without changing Scoring/AI/API layers.
    """
    key = (source_id or "google_maps").strip().lower()
    if key in {"google_maps", "google", "gmaps"}:
        from collectors.google_maps.production_crawler import GoogleMapsBranchReviewSource

        return GoogleMapsBranchReviewSource(
            headless=headless,
            max_branches=max_branches,
            max_reviews_per_branch=max_reviews_per_branch,
        )
    raise ValueError(
        f"Unknown crawl source {source_id!r}. "
        "Supported today: google_maps (extensible via collectors.sources.registry)."
    )


def build_source_for_company(
    company: CompanySpec,
    *,
    headless: bool = True,
    max_branches: int | None = None,
    max_reviews_per_branch: int | None = None,
) -> BranchReviewSource:
    return build_source(
        company.source,
        headless=headless,
        max_branches=max_branches,
        max_reviews_per_branch=max_reviews_per_branch,
    )
