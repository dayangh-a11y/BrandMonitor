from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from ai.adapters.fake import FakeAdapter
from ai.pipeline import AnalysisPipeline
from core.db import Database
from models.branch import Branch
from models.review import Review
from scoring.engine import ScoringEngine
from scoring.insights import InsightsGenerator


def test_api_serves_engine_scores(tmp_path: Path, monkeypatch):
    db_path = str(tmp_path / "api_score.db")
    monkeypatch.setenv("BRANDMONITOR_ENV", "development")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("ADMIN_TOKEN", "dev-admin-token")
    monkeypatch.setenv("AI_PROVIDER", "fake")

    async def seed() -> int:
        db = Database(db_path)
        await db.connect()
        cid = await db.upsert_company("ScoreCo")
        bid = await db.upsert_branch(
            cid, Branch(name="Main", address="Tehran", company_name="ScoreCo", place_id="s1")
        )
        pipeline = AnalysisPipeline(db, FakeAdapter())
        for i, (text, rating) in enumerate(
            [
                ("Worst delivery delay and package damage", 1.0),
                ("Great service and fast delivery", 5.0),
            ]
        ):
            rid = await db.upsert_review(
                bid,
                Review(
                    author=f"u{i}",
                    text=text,
                    rating=rating,
                    external_id=f"s-{i}",
                    branch_name="Main",
                ),
            )
            row = await db.get_review_row(rid)
            await pipeline.process_review(
                rid,
                Review(
                    author=row["author"],
                    text=row["text"],
                    rating=row["rating"],
                    external_id=row["external_id"],
                    branch_name=row["branch_name"],
                ),
            )
        await InsightsGenerator(db).refresh_company(cid, company_name="ScoreCo")
        await ScoringEngine(db).score_company(cid)
        await db.close()
        return cid

    company_id = asyncio.run(seed())

    from api.main import app

    with TestClient(app) as client:
        company = client.get(f"/companies/{company_id}")
        assert company.status_code == 200
        score = client.get(f"/companies/{company_id}/score")
        assert score.status_code == 200
        body = score.json()
        assert body["algorithm_version"] == "score_v1"
        assert 0 <= body["score"] <= 100
        assert "why" in body["components"]
        search = client.get("/search?q=ScoreCo")
        assert search.status_code == 200
        demo = client.get("/demo")
        assert demo.status_code == 200
        assert "ScoreCo" in demo.text or "Search" in demo.text
