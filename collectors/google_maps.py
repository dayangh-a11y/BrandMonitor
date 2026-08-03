"""Independent collector module entrypoint for Google Maps (keeps package intact)."""

from collectors.google_maps.production_crawler import GoogleMapsBranchReviewSource
from collectors.providers.google_maps_adapter import GoogleMapsProvider

__all__ = ["GoogleMapsBranchReviewSource", "GoogleMapsProvider"]
