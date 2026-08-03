"""Tipax pricing adapter — official eTipax OM Pricing API (credential-gated)."""

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

# Documented test host; production host may differ per Tipax onboarding.
DEFAULT_BASE = os.getenv("TIPAX_OM_BASE", "https://omtestapi.tipax.ir").rstrip("/")


class TipaxProvider:
    slug = "tipax"
    company = "Tipax"
    data_source = "tipax_etipax_om_api"

    def quote(self, request: QuoteRequest) -> QuoteResult:
        token = os.getenv("TIPAX_OM_TOKEN") or os.getenv("TIPAX_API_TOKEN")
        username = os.getenv("TIPAX_OM_USERNAME")
        password = os.getenv("TIPAX_OM_PASSWORD")

        if not token and not (username and password):
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message=(
                    "Tipax eTipax credentials not configured. Set TIPAX_OM_TOKEN "
                    "or TIPAX_OM_USERNAME/TIPAX_OM_PASSWORD. "
                    "Website ViewState calculator is intentionally not scraped."
                ),
            )

        try:
            if not token:
                token = self._login(username or "", password or "")
        except Exception as e:  # noqa: BLE001
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message=f"Tipax authentication failed: {e}",
                status="error",
            )

        origin_city = _city_id(request.origin)
        dest_city = _city_id(request.destination)
        if origin_city is None or dest_city is None:
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message="Tipax requires numeric origin/destination city_code (OM cityId).",
            )

        dims = request.dimensions
        body: dict[str, Any] = {
            "origin": {"cityId": origin_city},
            "destination": {"cityId": dest_city},
            "weight": request.weight_kg,
            "packType": _pack_type(request.package_type),
            "paymentType": 20 if request.cod else 10,
        }
        if request.declared_value is not None:
            body["packageValue"] = request.declared_value
        if dims.length_cm is not None:
            body["length"] = dims.length_cm
        if dims.width_cm is not None:
            body["width"] = dims.width_cm
        if dims.height_cm is not None:
            body["height"] = dims.height_cm
        if request.service_hint:
            body["Serviced"] = request.extras.get("serviced") or request.service_hint
        # Insurance: Tipax OM may require packing/content ids; without them we do not invent.
        if request.insurance and "packingId" not in request.extras:
            # still attempt quote; note limitation
            pass
        body.update({k: v for k, v in (request.extras or {}).items() if k not in body})

        url = f"{DEFAULT_BASE}/api/OM/v3/Pricing"
        try:
            status, payload = request_json(
                url,
                method="POST",
                json_body=body,
                headers={"Authorization": f"Bearer {token}"},
            )
        except HttpError as e:
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message=f"Tipax Pricing API error: {e}",
                status="error",
            )

        price, currency, breakdown, service_name, eta_min, eta_max, err = _parse_om_price(
            payload
        )
        if err or price is None:
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message=err or f"No price in Tipax response (HTTP {status}).",
                status="error" if status and status >= 400 else "unavailable",
            )

        note = None
        if request.insurance and "packingId" not in (request.extras or {}):
            note = "Insurance requested; confirm packing/insurance fields with Tipax OM docs."

        return QuoteResult(
            company=self.company,
            price=float(price),
            eta=format_eta_hours(eta_min, eta_max),
            currency=currency or "IRR",
            confidence=0.85,
            data_source=self.data_source,
            last_updated=utcnow_iso(),
            available=True,
            status="ok",
            message=note,
            provider_slug=self.slug,
            eta_hours_min=eta_min,
            eta_hours_max=eta_max,
            service_name=service_name,
            breakdown=breakdown,
            raw_refs={"http_status": status},
        )

    def _login(self, username: str, password: str) -> str:
        url = f"{DEFAULT_BASE}/api/OM/v3/Account/token"
        status, payload = request_json(
            url,
            method="POST",
            json_body={"username": username, "password": password},
        )
        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected token response (HTTP {status})")
        token = payload.get("token") or payload.get("access_token")
        data = payload.get("data")
        if token is None and isinstance(data, dict):
            token = data.get("token") or data.get("access_token")
        if not token:
            raise RuntimeError(f"No token in Tipax auth response (HTTP {status})")
        return str(token)


def _city_id(loc) -> int | None:
    code = loc.city_code
    if code is None:
        return None
    try:
        return int(str(code).strip())
    except (TypeError, ValueError):
        return None


def _pack_type(package_type: str) -> int:
    key = (package_type or "parcel").strip().casefold()
    mapping = {
        "envelope": 10,
        "packet": 10,
        "letter": 10,
        "parcel": 20,
        "package": 20,
        "box": 20,
        "mini_pack": 50,
        "minipack": 50,
    }
    return mapping.get(key, 20)


def _parse_om_price(
    payload: Any,
) -> tuple[
    float | None,
    str | None,
    dict[str, float],
    str | None,
    float | None,
    float | None,
    str | None,
]:
    if not isinstance(payload, dict):
        return None, None, {}, None, None, None, "Unexpected Tipax response type."
    # Tolerate common envelope shapes without inventing numbers.
    candidates = [payload]
    if isinstance(payload.get("data"), dict):
        candidates.append(payload["data"])
    if isinstance(payload.get("result"), dict):
        candidates.append(payload["result"])
    price = None
    currency = "IRR"
    breakdown: dict[str, float] = {}
    service_name = None
    for obj in candidates:
        for key in ("totalPrice", "price", "finalPrice", "amount", "total"):
            if obj.get(key) is not None:
                try:
                    price = float(obj[key])
                    break
                except (TypeError, ValueError):
                    continue
        if price is not None:
            for k, v in obj.items():
                if isinstance(v, (int, float)) and k.lower() not in {"status", "code"}:
                    breakdown[str(k)] = float(v)
            service_name = obj.get("serviceName") or obj.get("service") or service_name
            currency = obj.get("currency") or currency
            break
    if price is None:
        msg = payload.get("message") or payload.get("title") or "Price missing in OM response."
        return None, None, {}, None, None, None, str(msg)
    # OM pricing responses often omit ETA; do not invent one from YAML.
    return price, currency if isinstance(currency, str) else "IRR", breakdown, service_name, None, None, None


register_provider(TipaxProvider())
