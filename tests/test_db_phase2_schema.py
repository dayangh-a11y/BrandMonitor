"""Phase 2 / 2.1 schema verification — tables and indexes."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from core.db import Database

PHASE2_TABLES = {
    "review_analyses",
    "analysis_jobs",
    "branch_insights",
    "company_insights",
    "branch_scores",
    "company_scores",
}

PHASE2_INDEXES = {
    "idx_review_analyses_status",
    "idx_review_analyses_sentiment",
    "idx_review_analyses_input_hash",
    "idx_analysis_jobs_status",
    "idx_branch_scores_branch_calculated",
    "idx_company_scores_company_calculated",
}

REQUIRED_ANALYSIS_COLUMNS = {
    "complaint_categories",
    "positive_categories",
    "staff_behavior",
    "mentioned_employees",
    "mentioned_branch",
    "confidence_overall",
    "confidence_by_field",
    "input_hash",
    "provider",
    "model_id",
    "schema_version",
}


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "phase2_schema.db")


async def _connect(db_path: str) -> Database:
    db = Database(db_path)
    await db.connect()
    return db


def test_phase2_tables_and_indexes_exist(db_path: str):
    async def run() -> None:
        db = await _connect(db_path)
        try:
            assert db._conn is not None
            cursor = await db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row["name"] for row in await cursor.fetchall()}
            assert PHASE2_TABLES.issubset(tables)
            assert {"companies", "branches", "reviews"}.issubset(tables)

            cursor = await db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
            indexes = {row["name"] for row in await cursor.fetchall()}
            assert PHASE2_INDEXES.issubset(indexes)

            cursor = await db._conn.execute("PRAGMA table_info(review_analyses)")
            columns = {row["name"] for row in await cursor.fetchall()}
            assert REQUIRED_ANALYSIS_COLUMNS.issubset(columns)
        finally:
            await db.close()

    asyncio.run(run())


def test_review_analyses_fk_and_unique_review_id(db_path: str):
    async def run() -> None:
        db = await _connect(db_path)
        try:
            assert db._conn is not None
            now = "2026-08-02T00:00:00+00:00"
            await db._conn.execute(
                "INSERT INTO companies (name, source, created_at) VALUES (?, ?, ?)",
                ("Tipax", "google_maps", now),
            )
            await db._conn.execute(
                """
                INSERT INTO branches (
                    company_id, name, address, rating, review_count,
                    maps_url, place_id, collected_at
                ) VALUES (1, 'HQ', 'Tehran', 2.3, 10, '', '', ?)
                """,
                (now,),
            )
            await db._conn.execute(
                """
                INSERT INTO reviews (
                    branch_id, author, rating, text, published_at, language,
                    source, external_id, raw_json, collected_at
                ) VALUES (1, 'Ali', 1.0, 'bad', '', '', 'google_maps', 'r1', '{}', ?)
                """,
                (now,),
            )
            await db._conn.execute(
                """
                INSERT INTO review_analyses (
                    review_id, sentiment, complaint_categories, positive_categories,
                    status, provider, model_id, prompt_version, schema_version,
                    input_hash, created_at, updated_at
                ) VALUES (
                    1, 'Negative', '["delivery_speed"]', '[]',
                    'succeeded', 'fake', 'fake-v1', 'v1', 'analysis_dto_v1',
                    'hash1', ?, ?
                )
                """,
                (now, now),
            )
            await db._conn.commit()

            with pytest.raises(Exception):
                await db._conn.execute(
                    """
                    INSERT INTO review_analyses (
                        review_id, sentiment, complaint_categories, positive_categories,
                        status, provider, model_id, prompt_version, schema_version,
                        input_hash, created_at, updated_at
                    ) VALUES (
                        1, 'Negative', '[]', '[]',
                        'pending', 'fake', 'fake-v1', 'v1', 'analysis_dto_v1',
                        'hash2', ?, ?
                    )
                    """,
                    (now, now),
                )
                await db._conn.commit()
        finally:
            await db.close()

    asyncio.run(run())


def test_score_check_constraints(db_path: str):
    async def run() -> None:
        db = await _connect(db_path)
        try:
            assert db._conn is not None
            now = "2026-08-02T00:00:00+00:00"
            await db._conn.execute(
                "INSERT INTO companies (name, source, created_at) VALUES (?, ?, ?)",
                ("Tipax", "google_maps", now),
            )
            await db._conn.execute(
                """
                INSERT INTO branches (
                    company_id, name, address, rating, review_count,
                    maps_url, place_id, collected_at
                ) VALUES (1, 'HQ', 'Tehran', 2.3, 10, '', '', ?)
                """,
                (now,),
            )
            await db._conn.commit()

            with pytest.raises(Exception):
                await db._conn.execute(
                    """
                    INSERT INTO branch_scores (
                        branch_id, score, components, algorithm_version, calculated_at
                    ) VALUES (1, 150, '{}', 'score_v1', ?)
                    """,
                    (now,),
                )
                await db._conn.commit()
        finally:
            await db.close()

    asyncio.run(run())
