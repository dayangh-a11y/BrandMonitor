"""Mahex pricing adapter — website rate-calculation API."""

from __future__ import annotations

import os
import urllib.parse

from postal.pricing.http_util import HttpError, request_json
from postal.pricing.registry import register_provider
from postal.pricing.types import (
    QuoteRequest,
    QuoteResult,
    unavailable_result,
    utcnow_iso,
)

BASE = os.getenv("MAHEX_API_BASE", "https://mahex.com/website/api/").rstrip("/") + "/"


class MahexProvider:
    slug = "mahex"
    company = "Mahex"
    data_source = "mahex_website_api"

    def quote(self, request: QuoteRequest) -> QuoteResult:
        shipper = request.origin.city_code or request.origin.city_name
        consignee = request.destination.city_code or request.destination.city_name
        if not shipper or not consignee:
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message="Mahex requires origin/destination city_code (IR-*) or city_name.",
            )
        if request.declared_value is None:
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message="declared_value is required for Mahex quotes.",
            )
        dims = request.dimensions
        if dims.length_cm is None or dims.width_cm is None or dims.height_cm is None:
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message="length_cm, width_cm, and height_cm are required for Mahex quotes.",
            )
        if request.weight_kg > 45:
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message="Mahex website calculator rejects weight above 45 kg.",
                status="unsupported_route",
            )

        params = {
            "shipperCityCode": str(shipper),
            "consigneeCityCode": str(consignee),
            "totalGrossWeight": str(request.weight_kg),
            "totalDeclaredValue": str(int(request.declared_value)),
            "totalLength": str(dims.length_cm),
            "totalWidth": str(dims.width_cm),
            "totalHeight": str(dims.height_cm),
        }
        # COD / insurance are not clearly exposed on the public rate endpoint;
        # do not invent surcharges — surface as metadata only.
        url = BASE + "web/v1/rate-calculation?" + urllib.parse.urlencode(params)
        try:
            status, payload = request_json(url, method="GET")
        except HttpError as e:
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message=f"Mahex rate request failed: {e}",
                status="error",
            )

        amount = None
        if isinstance(payload, dict):
            amount = payload.get("totalAmount")
            if amount is None and isinstance(payload.get("data"), dict):
                amount = payload["data"].get("totalAmount")
        try:
            price = float(amount) if amount is not None else None
        except (TypeError, ValueError):
            price = None

        if price is None:
            msg = None
            if isinstance(payload, dict):
                msg = payload.get("message") or payload.get("description")
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message=str(msg or f"No totalAmount in Mahex response (HTTP {status})."),
                status="error" if status >= 400 else "unavailable",
            )

        note_bits = []
        if request.cod:
            note_bits.append("COD requested but not priced by this Mahex endpoint")
        if request.insurance:
            note_bits.append("Insurance requested but not priced by this Mahex endpoint")
        # ETA is not returned by the public rate-calculation endpoint.
        return QuoteResult(
            company=self.company,
            price=price,
            eta=None,
            currency="IRR",
            confidence=0.5,
            data_source=self.data_source,
            last_updated=utcnow_iso(),
            available=True,
            status="ok",
            message="; ".join(note_bits) if note_bits else None,
            provider_slug=self.slug,
            eta_hours_min=None,
            eta_hours_max=None,
            service_name=None,
            breakdown={"totalAmount": price},
            raw_refs={"http_status": status, "request_params": params},
        )


register_provider(MahexProvider())
