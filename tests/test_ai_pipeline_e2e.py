"""Unit + integration + E2E tests for AI foundation pipeline."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from ai.adapters.fake import FakeAdapter
from ai.pipeline import AnalysisPipeline
from ai.worker import AnalysisWorker
from core.db import Database
from models.branch import Branch
from models.review import Review


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "ai_foundation.db")


async def _seed_review(db: Database, text: str, external_id: str = "r1") -> int:
    company_id = await db.upsert_company("Tipax")
    branch_id = await db.upsert_branch(
        company_id,
        Branch(name="Tipax HQ", address="Tehran", rating=2.3, company_name="Tipax"),
    )
    review_id = await db.upsert_review(
        branch_id,
        Review(
            author="Ali",
            rating=1.0,
            text=text,
            published_at="1 day ago",
            external_id=external_id,
            branch_name="Tipax HQ",
        ),
    )
    return review_id


def test_fake_adapter_is_deterministic(db_path: str):
    async def run() -> None:
        adapter = FakeAdapter()
        review = Review(author="A", text="Worst delivery and bad tracking in Tehran", rating=1)
        first = await adapter.extract(review)
        second = await adapter.extract(review)
        assert first.sentiment == second.sentiment == "Negative"
        assert first.complaint_categories == second.complaint_categories
        assert "delivery_speed" in first.complaint_categories
        assert first.mentioned_city == "Tehran"
        assert first.raw_response["digest"] == second.raw_response["digest"]

    asyncio.run(run())


def test_pipeline_persists_validated_analysis(db_path: str):
    async def run() -> None:
        db = Database(db_path)
        await db.connect()
        try:
            review_id = await _seed_review(
                db,
                "Great service and fast delivery by Mr Karimi",
                external_id="pos-1",
            )
            row = await db.get_review_row(review_id)
            review = Review(
                author=row["author"],
                rating=row["rating"],
                text=row["text"],
                branch_name=row["branch_name"],
                external_id=row["external_id"],
            )
            pipeline = AnalysisPipeline(db, FakeAdapter())
            dto = await pipeline.process_review(review_id, review)
            assert dto.status == "succeeded"
            assert dto.sentiment == "Positive"

            saved = await db.get_analysis_dto(review_id)
            assert saved is not None
            assert saved.sentiment == "Positive"
            assert saved.provider == "fake"
            assert saved.model_id == "fake-v1"
            assert "customer_service" in saved.positive_categories
        finally:
            await db.close()

    asyncio.run(run())


def test_e2e_review_queue_worker_fake_validation_database(db_path: str):
    """E2E: Review -> Queue -> Worker -> FakeAdapter -> Validation -> Database."""

    async def run() -> None:
        db = Database(db_path)
        await db.connect()
        try:
            review_id = await _seed_review(
                db,
                "Bad delay and package damage in Tehran",
                external_id="e2e-1",
            )
            worker = AnalysisWorker(db, FakeAdapter())
            job_id = await worker.enqueue_review(review_id)
            assert job_id > 0

            results = await worker.run_until_idle()
            assert len(results) == 1
            assert results[0]["failed_items"] == 0
            assert results[0]["done_items"] == 1

            analysis = await db.get_analysis_dto(review_id)
            assert analysis is not None
            assert analysis.status == "succeeded"
            assert analysis.sentiment == "Negative"
            assert "delivery_speed" in analysis.complaint_categories
            assert analysis.package_damage is True
            assert analysis.mentioned_city == "Tehran"
            assert analysis.confidence_overall > 0.5

            stats = await db.stats()
            assert stats["reviews"] >= 1
            assert stats["review_analyses"] == 1
            assert stats["analysis_jobs"] == 1
        finally:
            await db.close()

    asyncio.run(run())
