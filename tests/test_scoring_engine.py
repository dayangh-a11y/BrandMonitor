from __future__ import annotations

import asyncio
from pathlib import Path

from ai.adapters.fake import FakeAdapter
from ai.pipeline import AnalysisPipeline
from core.db import Database
from models.branch import Branch
from models.review import Review
from scoring.engine import ScoringEngine, compute_branch_score_v1
from scoring.insights import InsightsGenerator


def test_score_v1_penalizes_negative_complaints():
    analyses = [
        {
            "status": "succeeded",
            "sentiment": "Negative",
            "complaint_categories": ["delivery_speed", "tracking"],
            "positive_categories": [],
            "delivery_speed": "slow",
            "customer_service": "bad",
            "staff_behavior": None,
            "package_damage": True,
            "pricing": None,
            "tracking": "bad",
            "professionalism": None,
            "urgency": "high",
            "confidence_overall": 0.9,
        },
        {
            "status": "succeeded",
            "sentiment": "Negative",
            "complaint_categories": ["delivery_speed"],
            "positive_categories": [],
            "delivery_speed": "slow",
            "customer_service": "bad",
            "urgency": "medium",
            "confidence_overall": 0.8,
        },
    ]
    result = compute_branch_score_v1(analyses)
    assert result.score < 55
    assert result.components["complaint_penalty"] < 0
    assert result.components["top_complaints"][0]["category"] == "delivery_speed"


def test_score_v1_rewards_positive_reviews():
    analyses = [
        {
            "status": "succeeded",
            "sentiment": "Positive",
            "complaint_categories": [],
            "positive_categories": ["customer_service", "delivery_speed"],
            "delivery_speed": "fast",
            "customer_service": "good",
            "staff_behavior": "good",
            "package_damage": False,
            "urgency": "low",
            "confidence_overall": 0.9,
        }
    ] * 4
    result = compute_branch_score_v1(analyses)
    assert result.score > 60
    assert result.components["positive_reward"] > 0


def test_e2e_analyze_score_insights_api_shape(tmp_path: Path):
    async def run() -> None:
        db = Database(str(tmp_path / "mvp.db"))
        await db.connect()
        company_id = await db.upsert_company("TipaxMVP")
        branch_id = await db.upsert_branch(
            company_id,
            Branch(name="HQ", address="Tehran", company_name="TipaxMVP", place_id="m1"),
        )
        texts = [
            ("Worst delivery delay and damage", 1.0, "e1"),
            ("Great service and fast delivery", 5.0, "e2"),
            ("Expensive pricing and bad tracking", 1.0, "e3"),
        ]
        pipeline = AnalysisPipeline(db, FakeAdapter())
        for text, rating, ext in texts:
            rid = await db.upsert_review(
                branch_id,
                Review(author="A", text=text, rating=rating, external_id=ext, branch_name="HQ"),
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

        insights = InsightsGenerator(db)
        insight = await insights.refresh_company(company_id, company_name="TipaxMVP")
        assert insight["review_count_used"] >= 1
        assert "TipaxMVP" in insight["summary"]

        engine = ScoringEngine(db)
        company_score = await engine.score_company(company_id)
        assert 0 <= company_score.score <= 100
        assert "branch_scores" in company_score.components
        assert "why" in company_score.components

        stored = await db.get_company_score(company_id)
        branch_stored = await db.get_branch_score(branch_id)
        assert stored is not None
        assert branch_stored is not None
        assert stored["algorithm_version"] == "score_v1"
        comps = branch_stored["components"]
        if isinstance(comps, str):
            import json

            comps = json.loads(comps)
        assert "sentiment_score" in comps
        assert "kappa" in comps
        await db.close()

    asyncio.run(run())
