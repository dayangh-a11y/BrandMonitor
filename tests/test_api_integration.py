from __future__ import annotations

import asyncio
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from api.deps import close_db, init_db
from api.main import app
from models.analysis import AnalysisDTO
from models.branch import Branch
from models.review import Review


async def _prepare(db_path: str) -> tuple[int, int]:
    db = await init_db(db_path)
    company_id = await db.upsert_company("Tipax")
    branch_id = await db.upsert_branch(
        company_id,
        Branch(
            name="Tipax HQ",
            address="Tehran Province, Tehran",
            rating=2.3,
            review_count=2,
            company_name="Tipax",
        ),
    )
    review_id = await db.upsert_review(
        branch_id,
        Review(
            author="Ali",
            rating=1.0,
            text="Bad delay in Tehran",
            published_at="1 day ago",
            external_id="r1",
            branch_name="Tipax HQ",
        ),
    )
    await db.upsert_review(
        branch_id,
        Review(
            author="Sara",
            rating=5.0,
            text="Great service",
            published_at="2 days ago",
            external_id="r2",
            branch_name="Tipax HQ",
        ),
    )
    await db.upsert_review_analysis(
        review_id,
        AnalysisDTO(
            sentiment="Negative",
            complaint_categories=["delivery_speed"],
            positive_categories=[],
            mentioned_city="Tehran",
            status="succeeded",
            provider="fake",
            model_id="fake-v1",
            confidence_overall=0.8,
        ),
        input_hash="h1",
    )
    assert db._conn is not None
    await db._conn.execute(
        """
        INSERT INTO branch_scores (branch_id, score, components, algorithm_version, calculated_at)
        VALUES (?, ?, '{}', 'score_v1', ?)
        """,
        (branch_id, 61.5, "2026-08-02T00:00:00+00:00"),
    )
    await db._conn.execute(
        """
        INSERT INTO company_scores (company_id, score, components, algorithm_version, calculated_at)
        VALUES (?, ?, '{}', 'score_v1', ?)
        """,
        (company_id, 60.0, "2026-08-02T00:00:00+00:00"),
    )
    await db._conn.commit()
    return company_id, branch_id


def test_api_companies_branches_reviews_scores_search(tmp_path: Path):
    async def run() -> None:
        db_path = str(tmp_path / "api.db")
        company_id, branch_id = await _prepare(db_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/companies")
            assert response.status_code == 200
            assert response.json()[0]["name"] == "Tipax"

            response = await ac.get(f"/companies/{company_id}")
            assert response.status_code == 200

            response = await ac.get("/companies/99999")
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "company_not_found"

            response = await ac.get(f"/companies/{company_id}/branches")
            assert response.status_code == 200
            assert response.json()[0]["id"] == branch_id

            response = await ac.get(f"/branches/{branch_id}")
            assert response.status_code == 200

            response = await ac.get(
                f"/branches/{branch_id}/reviews",
                params={
                    "limit": 10,
                    "offset": 0,
                    "sentiment": "Negative",
                    "category": "delivery_speed",
                    "city": "Tehran",
                    "sort": "newest",
                },
            )
            assert response.status_code == 200
            body = response.json()
            assert body["total"] == 1
            assert body["items"][0]["sentiment"] == "Negative"

            response = await ac.get(f"/branches/{branch_id}/score")
            assert response.status_code == 200
            assert response.json()["score"] == 61.5

            response = await ac.get(f"/companies/{company_id}/score")
            assert response.status_code == 200
            assert response.json()["score"] == 60.0

            response = await ac.get("/search", params={"q": "Tipax", "sort": "highest_score"})
            assert response.status_code == 200
            assert response.json()["companies"][0]["name"] == "Tipax"

            response = await ac.get("/search")
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "validation_error"

            response = await ac.get("/health")
            assert response.status_code == 200
            assert response.json()["status"] == "ok"

        await close_db()

    asyncio.run(run())
