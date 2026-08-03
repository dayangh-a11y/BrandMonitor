"""
Provider-agnostic multi-source review contracts.

New sources implement ReviewProvider and register in collectors.sources.registry
(or collectors.providers.registry) without changing Maps / Scoring / API cores.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Protocol


ProviderMode = Literal["live_maps", "official_api", "compliant_extractor", "manual_import"]


@dataclass
class UnifiedReview:
    """Canonical review row shared by every source adapter."""

    source: str
    brand: str
    branch: str = ""
    province: str = ""
    city: str = ""
    latitude: float | None = None
    longitude: float | None = None
    rating: float | None = None
    review: str = ""
    review_date: str = ""
    reviewer: str = ""
    reply: str = ""
    reply_date: str = ""
    photos_count: int | None = None
    url: str = ""
    scraped_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # Optional extras kept in metadata / app-store fields
    external_id: str = ""
    app_version: str = ""
    total_votes: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReviewProvider(Protocol):
    """
    Interchangeable adapter for a review source.

    Modes:
    - official_api: call vendor API when credentials/endpoints exist
    - compliant_extractor: approved extractor path (not fragile HTML scrapers)
    - manual_import: CSV/JSON datasets
    - live_maps: existing Google Maps Playwright collector
    """

    source_id: str
    display_name: str
    mode: ProviderMode

    def collect(self, brand: str, **kwargs: Any) -> list[UnifiedReview]:
        """Collect (or import) unified reviews for one brand."""
        ...

    def healthcheck(self) -> dict[str, Any]:
        """Return readiness: configured? api key? sample path?"""
        ...


@dataclass
class ProviderInfo:
    source_id: str
    display_name: str
    mode: ProviderMode
    implemented: bool
    notes: str
