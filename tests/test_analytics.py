from __future__ import annotations

import asyncio
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from analytics.filters import AnalyticsFilter
from analytics.service import AnalyticsService
from api.deps import close_db, init_db
from api.main import app
from models.branch import Branch
from models.review import Review
from scoring.engine import ScoringEngine
from scoring.insights import InsightsGenerator
from ai.adapters.fake import FakeAdapter
from ai.pipeline import AnalysisPipeline


async def _seed(db_path: str) -> tuple[int, int, int]:
    db = await init_db(db_path)
    c1 = await db.upsert_company("Tipax", source="test")
    c2 = await db.upsert_company("Chapar", source="test")
    b1 = await db.upsert_branch(
        c1,
        Branch(
            name="HQ",
            address="Tehran",
            city="Tehran",
            province="Tehran Province",
            rating=2.5,
            company_name="Tipax",
            place_id="t-hq",
        ),
    )
    b2 = await db.upsert_branch(
        c1,
        Branch(
            name="Vanak",
            address="Tehran Vanak",
            city="Tehran",
            province="Tehran Province",
            rating=3.5,
            company_name="Tipax",
            place_id="t-vanak",
        ),
    )
    b3 = await db.upsert_branch(
        c2,
        Branch(
            name="Center",
            address="Shiraz",
            city="Shiraz",
            province="Fars",
            rating=4.0,
            company_name="Chapar",
            place_id="c-center",
        ),
    )
    pipeline = AnalysisPipeline(db, FakeAdapter())
    samples = [
        (b1, 1.0, "Worst delivery delay and package damage"),
        (b1, 5.0, "Great service and fast delivery by Mr Karimi"),
        (b2, 2.0, "Expensive pricing and bad tracking"),
        (b2, 4.0, "Good professionalism and helpful staff"),
        (b3, 5.0, "Fast delivery and great customer service"),
        (b3, 3.0, "Average communication and fair pricing"),
    ]
    for i, (bid, rating, text) in enumerate(samples):
        rid = await db.upsert_review(
            bid,
            Review(
                author=f"u{i}",
                rating=rating,
                text=text,
                published_at="2026-07-01",
                external_id=f"a-{i}",
                branch_name="x",
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
    await InsightsGenerator(db).refresh_company(c1, company_name="Tipax")
    await InsightsGenerator(db).refresh_company(c2, company_name="Chapar")
    await ScoringEngine(db).score_company(c1)
    await ScoringEngine(db).score_company(c2)
    return c1, c2, b1


def test_company_and_branch_analytics_api(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("API_TOKEN", "dev-api-token")
    monkeypatch.setenv("ADMIN_TOKEN", "dev-admin-token")
    headers = {"X-API-Token": "dev-api-token"}

    async def run() -> None:
        db_path = str(tmp_path / "analytics.db")
        c1, c2, b1 = await _seed(db_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            denied = await ac.get(f"/analytics/companies/{c1}")
            assert denied.status_code == 401

            company = await ac.get(f"/analytics/companies/{c1}", headers=headers)
            assert company.status_code == 200
            body = company.json()
            assert body["company_name"] == "Tipax"
            assert body["total_reviews"] >= 4
            assert "sentiment_distribution" in body
            assert "complaint_categories" in body
            assert "charts" in body
            assert body["overall_score"] is not None

            # cache hit on second call
            company2 = await ac.get(f"/analytics/companies/{c1}", headers=headers)
            assert company2.json().get("cache", {}).get("hit") is True

            branch = await ac.get(f"/analytics/branches/{b1}", headers=headers)
            assert branch.status_code == 200
            bbody = branch.json()
            assert bbody["branch_score"] is not None
            assert "delivery_speed_analysis" in bbody
            assert "improvement_suggestions" in bbody

            compare = await ac.get(
                "/analytics/compare",
                headers=headers,
                params={"mode": "company", "ids": f"{c1},{c2}"},
            )
            assert compare.status_code == 200
            assert len(compare.json()["comparison"]) == 2

            export = await ac.get(
                f"/analytics/companies/{c1}/export",
                headers=headers,
                params={"format": "csv"},
            )
            assert export.status_code == 200
            assert "Overall Score".encode() in export.content or b"overall_score" in export.content

            ui = await ac.get(f"/analytics/ui/companies/{c1}", headers=headers)
            assert ui.status_code == 200
            assert "BrandMonitor" in ui.text
            assert "Overall Score" in ui.text

            filtered = await ac.get(
                f"/analytics/companies/{c1}",
                headers=headers,
                params={"sentiment": "Negative", "refresh": "true"},
            )
            assert filtered.status_code == 200
            assert filtered.json()["filters"]["sentiment"] == "Negative"

        await close_db()

    asyncio.run(run())


def test_analytics_service_cache_and_exports(tmp_path: Path):
    async def run() -> None:
        from analytics.export import export_excel, export_pdf, export_json
        from core.db import Database

        db_path = str(tmp_path / "svc.db")
        # reuse seeder via init
        monkey_db = await init_db(db_path)
        c1, _, b1 = await _seed(db_path)
        svc = AnalyticsService(monkey_db, ttl_seconds=60)
        dash = await svc.company_dashboard(c1, AnalyticsFilter(trend_grain="monthly"))
        assert dash["total_branches"] >= 2
        assert dash["charts"]["sentiment_pie"]["type"] == "pie"
        excel = export_excel(dash)
        assert excel[:2] == b"PK"
        pdf = export_pdf(dash)
        assert pdf.startswith(b"%PDF")
        assert b"Tipax" in export_json(dash)
        branch = await svc.branch_dashboard(b1, AnalyticsFilter())
        assert branch["entity_type"] == "branch"
        await close_db()

    asyncio.run(run())
