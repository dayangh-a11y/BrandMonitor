"""Tests for the unified Pricing & ETA Engine."""

from __future__ import annotations

from postal.pricing.engine import PricingEngine, to_markdown_table
from postal.pricing.registry import (
    clear_registry,
    ensure_builtin_providers,
    list_providers,
    register_provider,
)
from postal.pricing.types import (
    Dimensions,
    Location,
    QuoteRequest,
    QuoteResult,
    unavailable_result,
    utcnow_iso,
)


def _req(**kwargs) -> QuoteRequest:
    base = dict(
        origin=Location(city_name="Tehran", city_code="1", lat=35.7, lng=51.4),
        destination=Location(city_name="Isfahan", city_code="2", lat=32.6, lng=51.6),
        weight_kg=1.0,
        dimensions=Dimensions(length_cm=20, width_cm=15, height_cm=10),
        package_type="parcel",
        cod=False,
        insurance=False,
        declared_value=500_000,
    )
    base.update(kwargs)
    return QuoteRequest(**base)


class _FakeOk:
    slug = "fake_ok"
    company = "FakeOK"
    data_source = "fake_ok_source"

    def quote(self, request: QuoteRequest) -> QuoteResult:
        return QuoteResult(
            company=self.company,
            price=1000,
            eta="1d",
            currency="IRR",
            confidence=0.8,
            data_source=self.data_source,
            last_updated=utcnow_iso(),
            available=True,
            status="ok",
            provider_slug=self.slug,
            eta_hours_min=24,
            eta_hours_max=24,
        )


class _FakeDown:
    slug = "fake_down"
    company = "FakeDown"
    data_source = "fake_down_source"

    def quote(self, request: QuoteRequest) -> QuoteResult:
        return unavailable_result(
            company=self.company,
            provider_slug=self.slug,
            data_source=self.data_source,
            message="Temporarily unavailable for test.",
        )


class _FakeBoom:
    slug = "fake_boom"
    company = "FakeBoom"
    data_source = "fake_boom_source"

    def quote(self, request: QuoteRequest) -> QuoteResult:
        raise RuntimeError("simulated outage")


def test_builtin_providers_register_without_hardcoding_in_engine():
    clear_registry()
    ensure_builtin_providers()
    slugs = {p.slug for p in list_providers()}
    assert {
        "tipax",
        "chapar",
        "mahex",
        "alopeyk",
        "post",
    }.issubset(slugs)


def test_compare_same_structure_and_no_invented_prices():
    clear_registry()
    register_provider(_FakeOk())
    register_provider(_FakeDown())
    register_provider(_FakeBoom())
    engine = PricingEngine(providers=list_providers(discover=False))
    out = engine.compare(_req())
    assert out["summary"]["providers_total"] == 3
    assert out["summary"]["providers_available"] == 1
    assert out["summary"]["cheapest_company"] == "FakeOK"

    required = {
        "company",
        "price",
        "eta",
        "currency",
        "confidence",
        "data_source",
        "last_updated",
    }
    for row in out["results"]:
        assert required.issubset(row.keys())
    down = next(r for r in out["results"] if r["company"] == "FakeDown")
    boom = next(r for r in out["results"] if r["company"] == "FakeBoom")
    assert down["available"] is False
    assert down["price"] is None
    assert down["eta"] is None
    assert "unavailable" in (down["status"] or "")
    assert boom["available"] is False
    assert boom["price"] is None
    assert boom["status"] == "error"
    assert "markdown_table" in out and "FakeOK" in out["markdown_table"]
    assert "csv_table" in out and "FakeDown" in out["csv_table"]


def test_credential_gated_builtins_report_unavailable_not_estimates():
    clear_registry()
    ensure_builtin_providers()
    engine = PricingEngine()
    # Tipax / AloPeyk / Post should not invent without credentials
    for slug in ("tipax", "alopeyk", "post"):
        result = engine.quote_one(slug, _req())
        assert result.available is False
        assert result.price is None
        assert result.eta is None
        assert result.status in {"unavailable", "error"}
        public = result.to_public_dict()
        assert public["company"]
        assert public["data_source"]
        assert public["last_updated"]
        assert public["confidence"] == 0.0


def test_markdown_table_headers():
    rows = [
        QuoteResult(
            company="A",
            price=10,
            eta="2d",
            currency="IRR",
            confidence=0.5,
            data_source="x",
            last_updated="t",
            provider_slug="a",
        )
    ]
    md = to_markdown_table(rows)
    assert "Company" in md and "Price" in md and "ETA" in md and "Confidence" in md
