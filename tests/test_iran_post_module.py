"""Tests for the dedicated Iran Post module."""

from __future__ import annotations

from pathlib import Path

import pytest

from postal.iran_post.compare import compare, fair_comparison, national_ranking
from postal.iran_post.geo import coverage_percentage, normalize_city
from postal.iran_post.profile import load_official_profile, profile_public_view
from postal.iran_post.provider import IranPostModule

DB = Path("data/postal_intelligence.db")
pytestmark = pytest.mark.skipif(not DB.exists(), reason="postal_intelligence.db missing")


def test_profile_is_national_operator_not_regular_carrier():
    p = load_official_profile()
    assert p["role"] == "national_postal_operator"
    assert p["treat_as_regular_carrier"] is False
    view = profile_public_view(p)
    assert view["official_services"]
    assert view["official_pricing"]
    assert view["official_delivery_estimates"]
    assert view["service_coverage"]
    assert view["weight_limits"]
    assert view["size_limits"]
    assert view["insurance_rules"]
    assert view["tracking"]["public_only"] is True
    assert view["working_hours"]


def test_normalize_city_and_coverage():
    assert normalize_city("تهران") == "tehran"
    assert normalize_city("Tehran") == "tehran"
    assert coverage_percentage(31, 31) == 100.0
    assert coverage_percentage(0, 31) == 0.0


def test_catalog_declares_maintained_domains():
    cat = IranPostModule().catalog()
    assert cat["not_a_regular_carrier"] is True
    for key in (
        "official_services",
        "official_pricing",
        "official_delivery_estimates",
        "branch_directory",
        "service_coverage",
        "weight_and_size_limits",
        "insurance_rules",
        "tracking_information_public",
        "working_hours",
        "google_maps_reviews_post_offices",
    ):
        assert key in cat["maintains"]
    assert "coverage_percentage" in cat["display_metrics"]
    assert "confidence_score" in cat["display_metrics"]


def test_snapshot_includes_maps_reviews_and_warnings():
    snap = IranPostModule().snapshot()
    assert snap["role"] == "national_postal_operator"
    assert snap["maps_reviews"]["source_policy"] == "warehouse_google_maps_only"
    assert isinstance(snap["warnings"], list)
    assert snap["warnings"], "expected at least one national-scale warning"


def test_national_ranking_displays_required_metrics_and_warns():
    result = national_ranking()
    assert result.mode == "national_ranking"
    assert result.rows
    assert result.warnings, "unequal coverage / national operator warning required"
    cols = result.display["columns"]
    for col in (
        "coverage_percentage",
        "number_of_branches",
        "number_of_reviews",
        "confidence_score",
    ):
        assert col in cols
    post = next(r for r in result.rows if r["is_iran_post"])
    assert post["role"] == "national_postal_operator"


def test_fair_comparison_uses_intersection_or_refuses():
    result = fair_comparison(slugs=["post", "tipax", "chapar"])
    assert result.mode == "fair_comparison"
    assert "coverage_percentage" in (result.display.get("columns") or [])
    if result.eligible:
        assert result.common_cities
        # every row is constrained to the fair city universe
        for row in result.rows:
            assert row.get("fair_city_universe") == result.common_cities
    else:
        assert result.message
        assert "enough data" in result.message.lower() or result.common_cities == []


def test_compare_mode_dispatch():
    n = compare(mode="national")
    f = compare(mode="fair", slugs=["post", "tipax"])
    assert n["mode"] == "national_ranking"
    assert f["mode"] == "fair_comparison"
    with pytest.raises(ValueError):
        compare(mode="mystery")


def test_api_iran_post_routes_mounted():
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    headers = {"X-API-Token": "dev-api-token"}
    r = client.get("/postal/iran-post/catalog", headers=headers)
    assert r.status_code == 200
    assert r.json()["not_a_regular_carrier"] is True

    r = client.get("/postal/iran-post/profile", headers=headers)
    assert r.status_code == 200
    assert r.json()["slug"] == "post"

    r = client.get("/postal/iran-post/compare/national", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["warnings"]
    assert "coverage_percentage" in body["display"]["columns"]

    r = client.post(
        "/postal/iran-post/compare",
        headers=headers,
        json={"mode": "fair", "slugs": ["post", "tipax", "chapar"]},
    )
    assert r.status_code == 200
    assert r.json()["mode"] == "fair_comparison"
