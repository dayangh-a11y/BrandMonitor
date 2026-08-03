"""Shared request/response types for the Pricing & ETA Engine.

Every provider returns the same QuoteResult structure.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    return utcnow().isoformat()


@dataclass(frozen=True)
class Dimensions:
    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "length_cm": self.length_cm,
            "width_cm": self.width_cm,
            "height_cm": self.height_cm,
        }


@dataclass(frozen=True)
class Location:
    """Origin or destination. Providers map city_name/city_code as needed."""

    city_name: str | None = None
    city_code: str | None = None
    province: str | None = None
    lat: float | None = None
    lng: float | None = None
    postal_code: str | None = None

    def label(self) -> str:
        return (
            self.city_name
            or self.city_code
            or (
                f"{self.lat},{self.lng}"
                if self.lat is not None and self.lng is not None
                else "unknown"
            )
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "city_name": self.city_name,
            "city_code": self.city_code,
            "province": self.province,
            "lat": self.lat,
            "lng": self.lng,
            "postal_code": self.postal_code,
        }


@dataclass(frozen=True)
class QuoteRequest:
    origin: Location
    destination: Location
    weight_kg: float
    dimensions: Dimensions = field(default_factory=Dimensions)
    package_type: str = "parcel"  # parcel | envelope | mini_pack | …
    cod: bool = False
    insurance: bool = False
    declared_value: float | None = None  # major currency units as provided by caller
    currency: str = "IRR"
    service_hint: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "origin": self.origin.as_dict(),
            "destination": self.destination.as_dict(),
            "weight_kg": self.weight_kg,
            "dimensions": self.dimensions.as_dict(),
            "package_type": self.package_type,
            "cod": self.cod,
            "insurance": self.insurance,
            "declared_value": self.declared_value,
            "currency": self.currency,
            "service_hint": self.service_hint,
            "extras": self.extras,
        }


@dataclass
class QuoteResult:
    """Canonical provider output — identical keys for every carrier."""

    company: str
    price: float | None
    eta: str | None
    currency: str | None
    confidence: float
    data_source: str
    last_updated: str
    available: bool = True
    status: str = "ok"  # ok | unavailable | error | unsupported_route
    message: str | None = None
    provider_slug: str = ""
    eta_hours_min: float | None = None
    eta_hours_max: float | None = None
    service_name: str | None = None
    breakdown: dict[str, float] = field(default_factory=dict)
    raw_refs: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        """Exact public comparison structure required by the product."""
        return {
            "company": self.company,
            "price": self.price,
            "eta": self.eta,
            "currency": self.currency,
            "confidence": round(float(self.confidence), 3),
            "data_source": self.data_source,
            "last_updated": self.last_updated,
            "available": self.available,
            "status": self.status,
            "message": self.message,
            "provider_slug": self.provider_slug,
            "eta_hours_min": self.eta_hours_min,
            "eta_hours_max": self.eta_hours_max,
            "service_name": self.service_name,
            "breakdown": self.breakdown,
        }

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def unavailable_result(
    *,
    company: str,
    provider_slug: str,
    data_source: str,
    message: str,
    status: str = "unavailable",
    confidence: float = 0.0,
) -> QuoteResult:
    """Standard unavailable response — never invents a price/ETA."""
    return QuoteResult(
        company=company,
        price=None,
        eta=None,
        currency=None,
        confidence=confidence,
        data_source=data_source,
        last_updated=utcnow_iso(),
        available=False,
        status=status,
        message=message,
        provider_slug=provider_slug,
    )


def format_eta_hours(
    hours_min: float | None, hours_max: float | None = None
) -> str | None:
    if hours_min is None and hours_max is None:
        return None
    if hours_min is not None and hours_max is not None and hours_min != hours_max:
        return f"{_hours_label(hours_min)}–{_hours_label(hours_max)}"
    h = hours_min if hours_min is not None else hours_max
    assert h is not None
    return _hours_label(h)


def _hours_label(hours: float) -> str:
    if hours < 24:
        if hours == int(hours):
            return f"{int(hours)}h"
        return f"{hours:.1f}h"
    days = hours / 24.0
    if abs(days - round(days)) < 1e-6:
        d = int(round(days))
        return f"{d}d"
    return f"{days:.1f}d"
