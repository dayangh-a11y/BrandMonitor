"""Iran Post pricing adapter — merchant/gateway API (credential-gated).

Does not invent tariffs from PDF rate books at request time. Without
configured credentials the provider reports unavailable.
"""

from __future__ import annotations

import os
from typing import Any

from postal.pricing.http_util import HttpError, request_json
from postal.pricing.registry import register_provider
from postal.pricing.types import (
    QuoteRequest,
    QuoteResult,
    unavailable_result,
    utcnow_iso,
)

# Optional gateway (e.g. Tapin public post-office check-price) — only used when
# explicitly configured. Default empty → unavailable without guessing.
PRICE_URL = os.getenv("IRAN_POST_PRICE_URL", "").strip()


class IranPostProvider:
    slug = "post"
    company = "Iran Post"
    data_source = "iran_post_merchant_api"

    def quote(self, request: QuoteRequest) -> QuoteResult:
        token = (
            os.getenv("IRAN_POST_TOKEN")
            or os.getenv("IRAN_POST_API_TOKEN")
            or os.getenv("POST_ECOMMERCE_TOKEN")
        )
        shop_id = os.getenv("IRAN_POST_SHOP_ID")
        if not PRICE_URL or not (token or shop_id):
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message=(
                    "Iran Post live quoting is not configured. Set IRAN_POST_PRICE_URL "
                    "plus IRAN_POST_TOKEN and/or IRAN_POST_SHOP_ID after merchant onboarding. "
                    "Static PDF rate books are not auto-estimated."
                ),
            )

        origin_city = request.origin.city_code
        dest_city = request.destination.city_code
        origin_prov = request.origin.province
        dest_prov = request.destination.province
        if not origin_city or not dest_city:
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message="Iran Post requires origin/destination city_code (and preferably province).",
            )
        if request.declared_value is None:
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message="declared_value is required for Iran Post price checks.",
            )

        # Weight for many Post gateways is grams.
        weight_g = int(round(float(request.weight_kg) * 1000))
        pay_type = "2" if request.cod else "1"
        order_type = str(request.extras.get("order_type") or "1")  # 0 custom, 1 express-ish
        body: dict[str, Any] = {
            "price": str(int(request.declared_value)),
            "weight": str(weight_g),
            "order_type": order_type,
            "pay_type": pay_type,
            "from_city": str(origin_city),
            "to_city": str(dest_city),
        }
        if origin_prov:
            body["from_province"] = str(origin_prov)
        if dest_prov:
            body["to_province"] = str(dest_prov)
        if shop_id:
            body["shop_id"] = shop_id

        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
            # some gateways use custom token headers
            headers["token"] = token

        try:
            status, payload = request_json(
                PRICE_URL, method="POST", json_body=body, headers=headers
            )
        except HttpError as e:
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message=f"Iran Post price request failed: {e}",
                status="error",
            )

        price, currency, breakdown, err = _parse_post_price(payload)
        if err or price is None:
            return unavailable_result(
                company=self.company,
                provider_slug=self.slug,
                data_source=self.data_source,
                message=err or f"No price in Iran Post response (HTTP {status}).",
                status="error" if status and status >= 400 else "unavailable",
            )

        # ETA not reliably returned by gateway price checks — do not invent.
        note = None
        if request.insurance:
            note = "Insurance requested; not separately priced unless gateway returns it."

        return QuoteResult(
            company=self.company,
            price=float(price),
            eta=None,
            currency=currency or "IRR",
            confidence=0.75,
            data_source=self.data_source,
            last_updated=utcnow_iso(),
            available=True,
            status="ok",
            message=note,
            provider_slug=self.slug,
            eta_hours_min=None,
            eta_hours_max=None,
            service_name=f"order_type={order_type}",
            breakdown=breakdown,
            raw_refs={"http_status": status},
        )


def _parse_post_price(
    payload: Any,
) -> tuple[float | None, str | None, dict[str, float], str | None]:
    if not isinstance(payload, dict):
        return None, None, {}, "Unexpected Iran Post response type."
    entries = payload.get("entries") if isinstance(payload.get("entries"), dict) else None
    obj = entries or payload.get("data") or payload
    if not isinstance(obj, dict):
        return None, None, {}, "Price payload missing object."
    total = obj.get("total") or obj.get("send_price") or obj.get("price")
    try:
        price = float(total) if total is not None else None
    except (TypeError, ValueError):
        price = None
    if price is None:
        msg = None
        returns = payload.get("returns")
        if isinstance(returns, dict):
            msg = returns.get("message")
        return None, None, {}, str(msg or "Price missing in Iran Post response.")
    breakdown: dict[str, float] = {}
    for key in ("send_price", "just_send_price", "tax", "total"):
        if obj.get(key) is not None:
            try:
                breakdown[key] = float(obj[key])
            except (TypeError, ValueError):
                pass
    return price, "IRR", breakdown, None


register_provider(IranPostProvider())
