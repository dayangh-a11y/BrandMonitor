"""Provider registry — add a source in one registration call."""

from __future__ import annotations

from typing import Any, Callable

from collectors.providers.balad import BaladProvider
from collectors.providers.base import ProviderInfo, ReviewProvider
from collectors.providers.cafebazaar import CafeBazaarProvider
from collectors.providers.google_maps_adapter import GoogleMapsProvider
from collectors.providers.myket import MyketProvider
from collectors.providers.neshan import NeshanProvider

_FACTORY: dict[str, Callable[..., ReviewProvider]] = {
    "google_maps": GoogleMapsProvider,
    "neshan": NeshanProvider,
    "balad": BaladProvider,
    "cafebazaar": CafeBazaarProvider,
    "myket": MyketProvider,
}

PROVIDER_CATALOG: list[ProviderInfo] = [
    ProviderInfo("google_maps", "Google Maps", "live_maps", True, "Existing Playwright collector + DB adapter"),
    ProviderInfo("neshan", "نشان", "manual_import", True, "No stable public API — import adapter only"),
    ProviderInfo("balad", "بلد", "manual_import", True, "No stable public API — import adapter only"),
    ProviderInfo("cafebazaar", "کافه بازار", "manual_import", True, "No stable public API — import adapter only"),
    ProviderInfo("myket", "مایکت", "manual_import", True, "No stable public API — import adapter only"),
    # Future placeholders (not wired until adapters exist)
    ProviderInfo("google_play", "Google Play", "official_api", False, "Planned"),
    ProviderInfo("app_store", "Apple App Store", "official_api", False, "Planned"),
    ProviderInfo("instagram", "Instagram", "official_api", False, "Planned"),
    ProviderInfo("x_twitter", "X (Twitter)", "official_api", False, "Planned"),
    ProviderInfo("reddit", "Reddit", "official_api", False, "Planned"),
    ProviderInfo("linkedin", "LinkedIn", "official_api", False, "Planned"),
    ProviderInfo("official_website", "Official Website", "compliant_extractor", False, "Planned"),
    ProviderInfo("news", "News", "compliant_extractor", False, "Planned"),
    ProviderInfo("complaint_portal", "Complaint Portal", "compliant_extractor", False, "Planned"),
]


def register_provider(source_id: str, factory: Callable[..., ReviewProvider]) -> None:
    _FACTORY[source_id.strip().lower()] = factory


def build_provider(source_id: str, **kwargs: Any) -> ReviewProvider:
    key = (source_id or "").strip().lower()
    if key not in _FACTORY:
        raise ValueError(
            f"Unknown provider {source_id!r}. Registered: {sorted(_FACTORY)}. "
            "See docs/ADD_NEW_SOURCE.md"
        )
    return _FACTORY[key](**kwargs)


def list_providers() -> list[dict[str, Any]]:
    return [
        {
            "source_id": p.source_id,
            "display_name": p.display_name,
            "mode": p.mode,
            "implemented": p.implemented,
            "notes": p.notes,
        }
        for p in PROVIDER_CATALOG
    ]
