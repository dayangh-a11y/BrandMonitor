"""AloPeyk pricing adapter — official v2 price/calc API (credential-gated)."""

from __future__ import annotations

import os
from typing import Any

from postal.pricing.http_util import HttpError, request_json
from postal.pricing.registry import register_provider
from postal.pricing.types import (
    QuoteRequest,
    QuoteResult,
    format_eta_hours,
    unavailable_result,
    utcnow_iso,
)

API_BASE = os.getenv("ALOPEYK_API_BASE", "https://api.alopeyk.com").rstrip("/")


class AloPeykProvider:
    slug = "alopeyk"
    company = "AloPeyk"
    data_source = "alopeyk_api_v2"

    def quote(self, request: QuoteRequest) -> QuoteResult:
        token = os.getenv("ALOPEYK_API_TOKEN") or os.getenv("ALOPEYK_TOKEN")
        if not token:
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message=(
                    "AloPeyk API token not configured. Set ALOPEYK_API_TOKEN "
                    "(see https://docs.alopeyk.com/)."
                ),
            )

        if (
            request.origin.lat is None
            or request.origin.lng is None
            or request.destination.lat is None
            or request.destination.lng is None
        ):
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message="AloPeyk requires origin/destination lat and lng.",
            )

        transport = (
            request.service_hint
            or request.extras.get("transport_type")
            or os.getenv("ALOPEYK_DEFAULT_TRANSPORT", "motorbike")
        )
        body: dict[str, Any] = {
            "transport_type": transport,
            "addresses": [
                {
                    "type": "origin",
                    "lat": str(request.origin.lat),
                    "lng": str(request.origin.lng),
                },
                {
                    "type": "destination",
                    "lat": str(request.destination.lat),
                    "lng": str(request.destination.lng),
                },
            ],
            "has_return": bool(request.extras.get("has_return", False)),
            "cashed": bool(request.cod),
        }

        url = f"{API_BASE}/api/v2/orders/price/calc"
        try:
            status, payload = request_json(
                url,
                method="POST",
                json_body=body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
        except HttpError as e:
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message=f"AloPeyk price/calc failed: {e}",
                status="error",
            )

        obj = _extract_object(payload)
        if obj is None:
            msg = None
            if isinstance(payload, dict):
                msg = payload.get("message") or payload.get("error")
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message=str(msg or f"Unexpected AloPeyk response (HTTP {status})."),
                status="error" if status and status >= 400 else "unavailable",
            )

        try:
            price = float(obj.get("price"))
        except (TypeError, ValueError):
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message="AloPeyk response missing numeric price.",
                status="unavailable",
            )

        duration_s = obj.get("duration")
        eta_hours = None
        try:
            if duration_s is not None:
                eta_hours = float(duration_s) / 3600.0
        except (TypeError, ValueError):
            eta_hours = None

        breakdown: dict[str, float] = {"price": price}
        if obj.get("price_with_return") is not None:
            try:
                breakdown["price_with_return"] = float(obj["price_with_return"])
            except (TypeError, ValueError):
                pass
        if obj.get("distance") is not None:
            try:
                breakdown["distance_m"] = float(obj["distance"])
            except (TypeError, ValueError):
                pass

        note = None
        if request.insurance:
            note = "Insurance flag accepted as input but not mapped onto AloPeyk on-demand price/calc."
        if request.weight_kg and request.weight_kg > 0:
            # weight is not an AloPeyk on-demand input — do not invent adjustments
            extra = "Weight/dimensions are not inputs to AloPeyk on-demand price/calc."
            note = f"{note} {extra}".strip() if note else extra

        # Docs/examples report Toman; normalize label explicitly.
        currency = os.getenv("ALOPEYK_CURRENCY", "IRT")

        return QuoteResult(
            company=self.company,
            price=price,
            eta=format_eta_hours(eta_hours, eta_hours),
            currency=currency,
            confidence=0.9,
            data_source=self.data_source,
            last_updated=utcnow_iso(),
            available=True,
            status="ok",
            message=note,
            provider_slug=self.slug,
            eta_hours_min=eta_hours,
            eta_hours_max=eta_hours,
            service_name=str(obj.get("transport_type") or transport),
            breakdown=breakdown,
            raw_refs={"http_status": status},
        )


def _extract_object(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("object"), dict):
        return payload["object"]
    if isinstance(payload.get("data"), dict) and "price" in payload["data"]:
        return payload["data"]
    if "price" in payload:
        return payload
    return None


register_provider(AloPeykProvider())
