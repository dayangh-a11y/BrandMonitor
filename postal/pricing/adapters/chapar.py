"""Chapar pricing adapter — CDN quote + time-estimate APIs."""

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

CITY_URL = os.getenv("CHAPAR_CITY_URL", "https://apigmlch.ir/v1/get_city")
QUOTE_URL = os.getenv(
    "CHAPAR_QUOTE_URL",
    "https://cdn.chaparnet.com/api/page/calculate-shipping-costs/request",
)
ETA_URL = os.getenv("CHAPAR_ETA_URL", "https://cdn.chaparnet.com/api/time-estimate")


class ChaparProvider:
    slug = "chapar"
    company = "Chapar"
    data_source = "chapar_cdn_api"

    def __init__(self) -> None:
        self._city_cache: dict[str, int] | None = None

    def quote(self, request: QuoteRequest) -> QuoteResult:
        try:
            origin_id = self._resolve_city_id(request.origin.city_code or request.origin.city_name)
            dest_id = self._resolve_city_id(
                request.destination.city_code or request.destination.city_name
            )
        except Exception as e:  # noqa: BLE001
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message=f"City resolution failed: {e}",
                status="unavailable",
            )

        if origin_id is None or dest_id is None:
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message=(
                    "Could not resolve origin/destination to Chapar city ids. "
                    "Pass city_code as numeric id or a known city_name."
                ),
                status="unavailable",
            )

        value = request.declared_value
        if value is None:
            # Chapar UI requires value; without it we cannot honestly quote.
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message="declared_value is required for Chapar quotes.",
                status="unavailable",
            )

        method = str(request.extras.get("method") or "1")
        form = {
            "Origin": str(origin_id),
            "Destination": str(dest_id),
            "Weight": str(request.weight_kg),
            "Value": str(int(value)),
            "Method": method,
            "SenderCode": str(request.extras.get("sender_code") or "1000"),
            "ReceiverCode": str(request.extras.get("receiver_code") or "1000"),
            "Cod": "1" if request.cod else "0",
        }

        try:
            status, payload = request_json(QUOTE_URL, method="POST", form_body=form)
        except HttpError as e:
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message=f"Quote request failed: {e}",
                status="error",
            )

        price, currency, breakdown, service_name, err = _parse_quote_payload(payload)
        if err or price is None:
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message=err or f"No price in response (HTTP {status}).",
                status="unsupported_route" if status == 200 else "error",
            )

        eta_hours_min, eta_hours_max, eta_refs = self._fetch_eta(origin_id, dest_id)
        return QuoteResult(
            company=self.company,
            price=float(price),
            eta=format_eta_hours(eta_hours_min, eta_hours_max),
            currency=currency or "IRR",
            confidence=0.7 if eta_hours_min is not None else 0.55,
            data_source=self.data_source,
            last_updated=utcnow_iso(),
            available=True,
            status="ok",
            message=None,
            provider_slug=self.slug,
            eta_hours_min=eta_hours_min,
            eta_hours_max=eta_hours_max,
            service_name=service_name,
            breakdown=breakdown,
            raw_refs={"quote_http_status": status, "eta": eta_refs},
        )

    def _fetch_eta(
        self, origin_id: int, dest_id: int
    ) -> tuple[float | None, float | None, Any]:
        try:
            status, payload = request_json(
                ETA_URL,
                method="POST",
                json_body={"origin": origin_id, "destination": dest_id},
            )
        except HttpError as e:
            return None, None, {"error": str(e)}
        hours: list[float] = []
        data = payload.get("data") if isinstance(payload, dict) else None
        objects = (data or {}).get("objects") if isinstance(data, dict) else None
        if isinstance(objects, list):
            for row in objects:
                if isinstance(row, dict) and row.get("hour") is not None:
                    try:
                        hours.append(float(row["hour"]))
                    except (TypeError, ValueError):
                        continue
        if not hours:
            return None, None, {"http_status": status, "payload": payload}
        return min(hours), max(hours), {"http_status": status, "hours": hours}

    def _resolve_city_id(self, value: str | None) -> int | None:
        if value is None or str(value).strip() == "":
            return None
        text = str(value).strip()
        if text.isdigit():
            return int(text)
        mapping = self._load_cities()
        key = text.casefold()
        if key in mapping:
            return mapping[key]
        # fuzzy contains
        for name, cid in mapping.items():
            if key in name or name in key:
                return cid
        return None

    def _load_cities(self) -> dict[str, int]:
        if self._city_cache is not None:
            return self._city_cache
        cache: dict[str, int] = {}
        try:
            status, payload = request_json(CITY_URL)
        except HttpError:
            self._city_cache = cache
            return cache
        rows = payload
        if isinstance(payload, dict):
            rows = payload.get("data") or payload.get("objects") or payload.get("cities") or []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                cid = row.get("id") or row.get("city_id") or row.get("code")
                name = row.get("name") or row.get("city_name") or row.get("title")
                if cid is None or not name:
                    continue
                try:
                    cache[str(name).strip().casefold()] = int(cid)
                except (TypeError, ValueError):
                    continue
        self._city_cache = cache
        return cache


def _parse_quote_payload(
    payload: Any,
) -> tuple[float | None, str | None, dict[str, float], str | None, str | None]:
    if not isinstance(payload, dict):
        return None, None, {}, None, "Unexpected non-JSON quote response."
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if data.get("result") is False:
        return None, None, {}, None, str(data.get("message") or payload.get("message") or "Route unavailable.")
    objects = data.get("objects") or {}
    order = objects.get("order") if isinstance(objects, dict) else None
    if not isinstance(order, dict):
        # some responses nest differently
        return None, None, {}, None, str(data.get("message") or "No order object in quote response.")
    price_obj = order.get("price") if isinstance(order.get("price"), dict) else {}
    total = price_obj.get("fld_Total_Cost")
    if total is None:
        total = order.get("quote") or price_obj.get("total")
    try:
        price = float(total) if total is not None else None
    except (TypeError, ValueError):
        price = None
    breakdown: dict[str, float] = {}
    for key in (
        "fld_Manual_Cost",
        "fld_Pack_Cost",
        "fld_Charge_Cost",
        "fld_Manual_Insurance",
        "fld_Lab_Cost",
        "fld_Manual_VAT",
        "fld_Total_Cost",
    ):
        if key in price_obj and price_obj[key] is not None:
            try:
                breakdown[key] = float(price_obj[key])
            except (TypeError, ValueError):
                pass
    currency = order.get("currency") or "IRR"
    service_name = order.get("method_name")
    return price, currency if isinstance(currency, str) else "IRR", breakdown, service_name, None


register_provider(ChaparProvider())
