"""Unified Pricing & ETA Engine — compare all registered providers."""

from __future__ import annotations

import csv
import io
from typing import Any, Iterable, Sequence

from postal.pricing.base import PricingProvider
from postal.pricing.registry import get_provider, list_providers
from postal.pricing.types import QuoteRequest, QuoteResult, utcnow_iso


class PricingEngine:
    """Carrier-agnostic orchestration.

    Carriers are never hardcoded here — they come from the registry.
    Adding a future provider = drop in one adapter module that registers itself.
    """

    def __init__(self, providers: Sequence[PricingProvider] | None = None):
        self._providers = list(providers) if providers is not None else None

    def providers(self) -> list[PricingProvider]:
        if self._providers is not None:
            return list(self._providers)
        return list_providers()

    def quote_one(self, slug: str, request: QuoteRequest) -> QuoteResult:
        provider = get_provider(slug)
        if provider is None:
            return QuoteResult(
                company=slug,
                price=None,
                eta=None,
                currency=None,
                confidence=0.0,
                data_source="registry",
                last_updated=utcnow_iso(),
                available=False,
                status="unavailable",
                message=f"No pricing provider registered for slug '{slug}'.",
                provider_slug=slug,
            )
        return self._safe_quote(provider, request)

    def compare(
        self,
        request: QuoteRequest,
        *,
        slugs: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        providers = self.providers()
        if slugs is not None:
            wanted = {s.strip().lower() for s in slugs}
            providers = [p for p in providers if p.slug in wanted]
            # include explicit unavailable rows for missing requested slugs
            have = {p.slug for p in providers}
            missing = sorted(wanted - have)
        else:
            missing = []

        results: list[QuoteResult] = []
        for provider in providers:
            results.append(self._safe_quote(provider, request))
        for slug in missing:
            results.append(
                QuoteResult(
                    company=slug,
                    price=None,
                    eta=None,
                    currency=None,
                    confidence=0.0,
                    data_source="registry",
                    last_updated=utcnow_iso(),
                    available=False,
                    status="unavailable",
                    message=f"No pricing provider registered for slug '{slug}'.",
                    provider_slug=slug,
                )
            )

        # sort: available with price first (ascending), then unavailable
        def sort_key(r: QuoteResult) -> tuple:
            if r.available and r.price is not None:
                return (0, float(r.price), r.company)
            return (1, float("inf"), r.company)

        results.sort(key=sort_key)
        public = [r.to_public_dict() for r in results]
        available = [r for r in results if r.available and r.price is not None]
        return {
            "request": request.as_dict(),
            "generated_at": utcnow_iso(),
            "results": public,
            "table": {
                "columns": [
                    "company",
                    "price",
                    "eta",
                    "currency",
                    "confidence",
                    "data_source",
                    "last_updated",
                    "status",
                    "message",
                ],
                "rows": [
                    [
                        r["company"],
                        r["price"],
                        r["eta"],
                        r["currency"],
                        r["confidence"],
                        r["data_source"],
                        r["last_updated"],
                        r["status"],
                        r["message"],
                    ]
                    for r in public
                ],
            },
            "summary": {
                "providers_total": len(results),
                "providers_available": len(available),
                "providers_unavailable": len(results) - len(available),
                "cheapest_company": available[0].company if available else None,
                "cheapest_price": available[0].price if available else None,
                "fastest_company": _fastest(available).company if available else None,
                "fastest_eta": _fastest(available).eta if available else None,
            },
            "markdown_table": to_markdown_table(results),
            "csv_table": to_csv_table(results),
        }

    @staticmethod
    def _safe_quote(provider: PricingProvider, request: QuoteRequest) -> QuoteResult:
        try:
            result = provider.quote(request)
        except Exception as e:  # noqa: BLE001 — boundary: never invent prices
            return QuoteResult(
                company=provider.company,
                price=None,
                eta=None,
                currency=None,
                confidence=0.0,
                data_source=provider.data_source,
                last_updated=utcnow_iso(),
                available=False,
                status="error",
                message=f"Provider raised {type(e).__name__}: {e}",
                provider_slug=provider.slug,
            )
        # normalize identity fields
        if not result.provider_slug:
            result.provider_slug = provider.slug
        if not result.company:
            result.company = provider.company
        if not result.data_source:
            result.data_source = provider.data_source
        # hard guard: never allow fabricated availability without price evidence
        if result.available and result.price is None and result.status == "ok":
            result.available = False
            result.status = "unavailable"
            result.message = (
                result.message
                or "Provider marked available but returned no price; treated as unavailable."
            )
            result.confidence = 0.0
        return result


def _fastest(results: Sequence[QuoteResult]) -> QuoteResult:
    def key(r: QuoteResult) -> float:
        if r.eta_hours_min is not None:
            return float(r.eta_hours_min)
        if r.eta_hours_max is not None:
            return float(r.eta_hours_max)
        return float("inf")

    return min(results, key=key)


def to_markdown_table(results: Iterable[QuoteResult]) -> str:
    headers = [
        "Company",
        "Price",
        "ETA",
        "Currency",
        "Confidence",
        "Data Source",
        "Last Updated",
        "Status",
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for r in results:
        price = "—" if r.price is None else f"{r.price:,.0f}" if float(r.price).is_integer() else f"{r.price}"
        eta = r.eta or "—"
        currency = r.currency or "—"
        conf = f"{r.confidence:.0%}"
        status = r.status
        if not r.available and r.message:
            status = f"{r.status}: {r.message}"
        lines.append(
            "| "
            + " | ".join(
                [
                    r.company,
                    price,
                    eta,
                    currency,
                    conf,
                    r.data_source,
                    r.last_updated,
                    status.replace("|", "/"),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def to_csv_table(results: Iterable[QuoteResult]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "company",
            "price",
            "eta",
            "currency",
            "confidence",
            "data_source",
            "last_updated",
            "status",
            "message",
            "available",
        ]
    )
    for r in results:
        writer.writerow(
            [
                r.company,
                r.price,
                r.eta,
                r.currency,
                r.confidence,
                r.data_source,
                r.last_updated,
                r.status,
                r.message,
                r.available,
            ]
        )
    return buf.getvalue()
