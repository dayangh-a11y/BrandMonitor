"""Phase 11 geographic analytics tests (visualization only)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from ai.adapters.fake import FakeAdapter
from ai.pipeline import AnalysisPipeline
from analytics.filters import AnalyticsFilter
from analytics.geo_compute import build_geo_dashboard, normalize_province, score_color
from analytics.service import AnalyticsService
from api.deps import close_db, init_db
from api.main import app
from models.branch import Branch
from models.review import Review
from scoring.engine import ScoringEngine
from scoring.insights import InsightsGenerator


async def _seed_geo(db_path: str) -> int:
    db = await init_db(db_path)
    company_id = await db.upsert_company("Tipax", source="test")
    branches = [
        ("HQ", "Tehran", "Tehran", 2.5, 35.69, 51.39, "Worst delivery delay and package damage"),
        ("Vanak", "Tehran", "Tehran", 3.5, 35.76, 51.41, "Good professionalism and helpful staff"),
        ("Mashhad", "Mashhad", "Razavi Khorasan", 4.0, 36.30, 59.60, "Fast delivery and great customer service"),
        ("NoCoords", "Shiraz", "Fars", 3.0, None, None, "Average communication and fair pricing"),
    ]
    pipeline = AnalysisPipeline(db, FakeAdapter())
    for i, (name, city, province, rating, lat, lon, text) in enumerate(branches):
        bid = await db.upsert_branch(
            company_id,
            Branch(
                name=name,
                address=f"{province}, {city}",
                city=city,
                province=province,
                rating=rating,
                company_name="Tipax",
                place_id=f"geo-{i}",
                latitude=lat,
                longitude=lon,
            ),
        )
        for j, (rev_rating, rev_text) in enumerate(
            [
                (1.0 if i == 0 else 4.0 + (i % 2), text),
                (5.0 if i else 2.0, "Great service and fast delivery by Mr Karimi"),
            ]
        ):
            rid = await db.upsert_review(
                bid,
                Review(
                    author=f"u{i}-{j}",
                    rating=rev_rating,
                    text=rev_text,
                    published_at="2026-07-01",
                    external_id=f"geo-r-{i}-{j}",
                    branch_name=name,
                    source="test",
                ),
            )
            row = await db.get_review_row(rid)
            await pipeline.process_review(
                rid,
                Review(
                    author=row["author"],
                    rating=row["rating"],
                    text=row["text"],
                    external_id=row["external_id"],
                    branch_name=row["branch_name"],
                ),
            )
        await InsightsGenerator(db).refresh_branch(bid, branch_name=name)
    await InsightsGenerator(db).refresh_company(company_id, company_name="Tipax")
    await ScoringEngine(db).score_company(company_id)
    return company_id


def test_normalize_province_and_colors():
    assert normalize_province("Tehran Province") == "Tehran"
    assert normalize_province("تهران") == "Tehran"
    assert normalize_province("Esfahan") == "Isfahan"
    assert score_color(85) == "#15803d"
    assert score_color(70) == "#4ade80"
    assert score_color(55) == "#eab308"
    assert score_color(40) == "#f97316"
    assert score_color(20) == "#dc2626"
    assert score_color(None) == "#94a3b8"


def test_build_geo_dashboard_unit():
    company = {"id": 1, "name": "Tipax"}
    branches = [
        {
            "id": 1,
            "name": "A",
            "city": "Tehran",
            "province": "Tehran",
            "rating": 4.0,
            "latest_score": 82,
            "latitude": 35.7,
            "longitude": 51.4,
            "review_count": 2,
        },
        {
            "id": 2,
            "name": "B",
            "city": "Shiraz",
            "province": "Fars",
            "rating": 2.0,
            "latest_score": 30,
            "latitude": 29.6,
            "longitude": 52.5,
            "review_count": 1,
        },
    ]
    rows = [
        {
            "branch_id": 1,
            "sentiment": "Positive",
            "complaint_categories": [],
            "positive_categories": ["speed"],
            "confidence_overall": 0.9,
            "event_date": "2026-07-01",
            "review_rating": 5,
        },
        {
            "branch_id": 2,
            "sentiment": "Negative",
            "complaint_categories": ["delay"],
            "positive_categories": [],
            "confidence_overall": 0.7,
            "event_date": "2026-07-01",
            "review_rating": 1,
        },
    ]
    payload = build_geo_dashboard(
        company=company,
        branches=branches,
        rows=rows,
        insights_by_branch={},
        filt=AnalyticsFilter(),
    )
    assert payload["kpis"]["total_branches"] == 2
    assert len(payload["map_pins"]) == 2
    assert payload["top10_best"][0]["branch"] == "A"
    assert payload["top10_worst"][0]["branch"] == "B"
    assert len(payload["leaderboard"]) == 2
    assert "review_distribution" in payload
    assert "score_distribution" in payload


def test_geo_api_and_ui(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("API_TOKEN", "dev-api-token")
    monkeypatch.setenv("ADMIN_TOKEN", "dev-admin-token")
    headers = {"X-API-Token": "dev-api-token"}

    async def run() -> None:
        db_path = str(tmp_path / "geo.db")
        company_id = await _seed_geo(db_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            denied = await ac.get(f"/analytics/companies/{company_id}/geo")
            assert denied.status_code == 401

            geo = await ac.get(f"/analytics/companies/{company_id}/geo", headers=headers)
            assert geo.status_code == 200
            body = geo.json()
            assert body["entity_type"] == "geo_dashboard"
            assert body["kpis"]["total_branches"] >= 3
            assert body["kpis"]["branches_with_coordinates"] >= 3
            assert len(body["map_pins"]) >= 3
            assert "leaderboard" in body
            assert "province_heatmap" in body

            export = await ac.get(
                f"/analytics/companies/{company_id}/geo/export",
                headers=headers,
                params={"format": "csv"},
            )
            assert export.status_code == 200
            assert b"leaderboard" in export.content or b"kpis" in export.content

            ui = await ac.get(f"/analytics/ui/geo/{company_id}", headers=headers)
            assert ui.status_code == 200
            assert "Geographic Analytics" in ui.text
            assert "plotly" in ui.text.lower()
            assert "leaderboard" in ui.text.lower()

            gj = await ac.get("/analytics/ui/geo/iran.geojson", headers=headers)
            assert gj.status_code == 200
            assert gj.json()["type"] == "FeatureCollection"
            assert len(gj.json()["features"]) == 31

        await close_db()

    asyncio.run(run())


def test_geo_service_direct(tmp_path: Path):
    async def run() -> None:
        db_path = str(tmp_path / "geo_svc.db")
        company_id = await _seed_geo(db_path)
        from api.deps import _DB

        svc = AnalyticsService(_DB, ttl_seconds=60)
        dash = await svc.geo_dashboard(company_id, AnalyticsFilter())
        assert dash["company_name"] == "Tipax"
        assert dash["kpis"]["coverage_pct"] is not None
        await close_db()

    asyncio.run(run())
