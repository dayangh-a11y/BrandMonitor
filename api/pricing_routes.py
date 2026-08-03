"""HTTP API for the unified Pricing & ETA Engine."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.auth import require_api_token
from postal.pricing import PricingEngine
from postal.pricing.registry import list_providers
from postal.pricing.types import Dimensions, Location, QuoteRequest

router = APIRouter(
    prefix="/postal/pricing",
    tags=["pricing-eta"],
    dependencies=[Depends(require_api_token)],
)


class LocationIn(BaseModel):
    city_name: str | None = None
    city_code: str | None = None
    province: str | None = None
    lat: float | None = None
    lng: float | None = None
    postal_code: str | None = None


class DimensionsIn(BaseModel):
    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None


class QuoteIn(BaseModel):
    origin: LocationIn
    destination: LocationIn
    weight_kg: float = Field(..., gt=0)
    dimensions: DimensionsIn = Field(default_factory=DimensionsIn)
    package_type: str = "parcel"
    cod: bool = False
    insurance: bool = False
    declared_value: float | None = None
    currency: str = "IRR"
    service_hint: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)
    providers: list[str] | None = None


def _to_request(body: QuoteIn) -> QuoteRequest:
    return QuoteRequest(
        origin=Location(**body.origin.model_dump()),
        destination=Location(**body.destination.model_dump()),
        weight_kg=body.weight_kg,
        dimensions=Dimensions(**body.dimensions.model_dump()),
        package_type=body.package_type,
        cod=body.cod,
        insurance=body.insurance,
        declared_value=body.declared_value,
        currency=body.currency,
        service_hint=body.service_hint,
        extras=body.extras,
    )


@router.get("/providers")
def pricing_providers() -> dict[str, Any]:
    providers = list_providers()
    return {
        "providers": [
            {
                "slug": p.slug,
                "company": p.company,
                "data_source": p.data_source,
            }
            for p in providers
        ]
    }


@router.post("/compare")
def pricing_compare(body: QuoteIn) -> dict[str, Any]:
    engine = PricingEngine()
    return engine.compare(_to_request(body), slugs=body.providers)


@router.post("/quote/{slug}")
def pricing_quote_one(slug: str, body: QuoteIn) -> dict[str, Any]:
    engine = PricingEngine()
    result = engine.quote_one(slug, _to_request(body))
    return result.to_public_dict()
