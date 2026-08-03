from __future__ import annotations

from collectors.company_config import CompanySpec
from collectors.sources.base import BranchReviewSource


def build_source(
    source_id: str,
    *,
    headless: bool = True,
    max_branches: int | None = None,
    max_reviews_per_branch: int | None = None,
    search_queries: list[str] | None = None,
) -> BranchReviewSource:
    """
    Factory for crawl sources.

    Additional sources (Neshan, Balad, Cafe Bazaar, Myket, …) register via
    collectors.providers — Maps live crawl stays here; import providers are
    used by scripts/run_multisource_pipeline.py.
    """
    key = (source_id or "google_maps").strip().lower()
    if key in {"google_maps", "google", "gmaps"}:
        from collectors.google_maps.production_crawler import GoogleMapsBranchReviewSource

        return GoogleMapsBranchReviewSource(
            headless=headless,
            max_branches=max_branches,
            max_reviews_per_branch=max_reviews_per_branch,
            search_queries=search_queries,
        )
    # Non-Maps providers are not Playwright BranchReviewSource crawlers.
    # Use collectors.providers.build_provider for unified multi-source ingest.
    raise ValueError(
        f"Unknown live crawl source {source_id!r}. "
        "Supported live crawl: google_maps. "
        "For neshan/balad/cafebazaar/myket use collectors.providers.build_provider "
        "or scripts/run_multisource_pipeline.py (manual_import / future official_api)."
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
