from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from models.branch import Branch
from models.review import Review


class Database:
    def __init__(self, path: str = "data/brandmonitor.db"):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._init_schema()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def _init_schema(self) -> None:
        assert self._conn is not None
        await self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL DEFAULT 'google_maps',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS branches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                address TEXT NOT NULL DEFAULT '',
                rating REAL NOT NULL DEFAULT 0,
                review_count INTEGER NOT NULL DEFAULT 0,
                maps_url TEXT NOT NULL DEFAULT '',
                place_id TEXT NOT NULL DEFAULT '',
                collected_at TEXT NOT NULL,
                UNIQUE(company_id, name, address),
                FOREIGN KEY(company_id) REFERENCES companies(id)
            );

            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                branch_id INTEGER NOT NULL,
                author TEXT NOT NULL DEFAULT '',
                rating REAL NOT NULL DEFAULT 0,
                text TEXT NOT NULL DEFAULT '',
                published_at TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'google_maps',
                external_id TEXT NOT NULL DEFAULT '',
                raw_json TEXT NOT NULL DEFAULT '{}',
                collected_at TEXT NOT NULL,
                UNIQUE(branch_id, external_id),
                FOREIGN KEY(branch_id) REFERENCES branches(id)
            );

            CREATE INDEX IF NOT EXISTS idx_reviews_branch_id ON reviews(branch_id);
            CREATE INDEX IF NOT EXISTS idx_branches_company_id ON branches(company_id);

            -- Phase 2: AI analysis + scoring schema
            CREATE TABLE IF NOT EXISTS review_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id INTEGER NOT NULL UNIQUE,
                sentiment TEXT NOT NULL DEFAULT 'neutral'
                    CHECK (sentiment IN ('positive', 'neutral', 'negative')),
                sentiment_score REAL NOT NULL DEFAULT 0
                    CHECK (sentiment_score >= -1.0 AND sentiment_score <= 1.0),
                urgency TEXT NOT NULL DEFAULT 'low'
                    CHECK (urgency IN ('low', 'medium', 'high')),
                categories TEXT NOT NULL DEFAULT '[]',
                mentioned_employee TEXT,
                mentioned_city TEXT,
                delivery_speed TEXT
                    CHECK (
                        delivery_speed IS NULL
                        OR delivery_speed IN ('fast', 'normal', 'slow')
                    ),
                package_damage INTEGER
                    CHECK (package_damage IS NULL OR package_damage IN (0, 1)),
                customer_service TEXT
                    CHECK (
                        customer_service IS NULL
                        OR customer_service IN ('good', 'bad')
                    ),
                pricing TEXT
                    CHECK (
                        pricing IS NULL
                        OR pricing IN ('fair', 'expensive')
                    ),
                tracking TEXT
                    CHECK (
                        tracking IS NULL
                        OR tracking IN ('good', 'bad')
                    ),
                professionalism TEXT
                    CHECK (
                        professionalism IS NULL
                        OR professionalism IN ('good', 'bad')
                    ),
                pros TEXT NOT NULL DEFAULT '[]',
                cons TEXT NOT NULL DEFAULT '[]',
                model_name TEXT NOT NULL DEFAULT '',
                prompt_version TEXT NOT NULL DEFAULT '',
                raw_response TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'succeeded', 'failed', 'skipped')),
                error TEXT,
                analyzed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(review_id) REFERENCES reviews(id)
            );

            CREATE TABLE IF NOT EXISTS analysis_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL
                    CHECK (scope IN ('review', 'branch', 'company', 'backfill')),
                scope_id INTEGER,
                status TEXT NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
                total_items INTEGER NOT NULL DEFAULT 0,
                done_items INTEGER NOT NULL DEFAULT 0,
                failed_items INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS branch_insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                branch_id INTEGER NOT NULL UNIQUE,
                summary TEXT NOT NULL DEFAULT '',
                pros TEXT NOT NULL DEFAULT '[]',
                cons TEXT NOT NULL DEFAULT '[]',
                common_categories TEXT NOT NULL DEFAULT '[]',
                review_count_used INTEGER NOT NULL DEFAULT 0,
                model_name TEXT NOT NULL DEFAULT '',
                prompt_version TEXT NOT NULL DEFAULT '',
                generated_at TEXT NOT NULL,
                FOREIGN KEY(branch_id) REFERENCES branches(id)
            );

            CREATE TABLE IF NOT EXISTS company_insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL UNIQUE,
                summary TEXT NOT NULL DEFAULT '',
                pros TEXT NOT NULL DEFAULT '[]',
                cons TEXT NOT NULL DEFAULT '[]',
                common_categories TEXT NOT NULL DEFAULT '[]',
                review_count_used INTEGER NOT NULL DEFAULT 0,
                model_name TEXT NOT NULL DEFAULT '',
                prompt_version TEXT NOT NULL DEFAULT '',
                generated_at TEXT NOT NULL,
                FOREIGN KEY(company_id) REFERENCES companies(id)
            );

            CREATE TABLE IF NOT EXISTS branch_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                branch_id INTEGER NOT NULL,
                score REAL NOT NULL
                    CHECK (score >= 0 AND score <= 100),
                components TEXT NOT NULL DEFAULT '{}',
                algorithm_version TEXT NOT NULL DEFAULT 'score_v1',
                calculated_at TEXT NOT NULL,
                FOREIGN KEY(branch_id) REFERENCES branches(id)
            );

            CREATE TABLE IF NOT EXISTS company_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                score REAL NOT NULL
                    CHECK (score >= 0 AND score <= 100),
                components TEXT NOT NULL DEFAULT '{}',
                algorithm_version TEXT NOT NULL DEFAULT 'score_v1',
                calculated_at TEXT NOT NULL,
                FOREIGN KEY(company_id) REFERENCES companies(id)
            );

            CREATE INDEX IF NOT EXISTS idx_review_analyses_status
                ON review_analyses(status);
            CREATE INDEX IF NOT EXISTS idx_review_analyses_sentiment
                ON review_analyses(sentiment);
            CREATE INDEX IF NOT EXISTS idx_analysis_jobs_status
                ON analysis_jobs(status);
            CREATE INDEX IF NOT EXISTS idx_branch_scores_branch_calculated
                ON branch_scores(branch_id, calculated_at);
            CREATE INDEX IF NOT EXISTS idx_company_scores_company_calculated
                ON company_scores(company_id, calculated_at);
            """
        )
        await self._conn.commit()

    async def upsert_company(self, name: str, source: str = "google_maps") -> int:
        assert self._conn is not None
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """
            INSERT INTO companies (name, source, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET source = excluded.source
            """,
            (name, source, now),
        )
        await self._conn.commit()
        cursor = await self._conn.execute(
            "SELECT id FROM companies WHERE name = ?",
            (name,),
        )
        row = await cursor.fetchone()
        assert row is not None
        return int(row["id"])

    async def upsert_branch(self, company_id: int, branch: Branch) -> int:
        assert self._conn is not None
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """
            INSERT INTO branches (
                company_id, name, address, rating, review_count,
                maps_url, place_id, collected_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company_id, name, address) DO UPDATE SET
                rating = excluded.rating,
                review_count = excluded.review_count,
                maps_url = excluded.maps_url,
                place_id = excluded.place_id,
                collected_at = excluded.collected_at
            """,
            (
                company_id,
                branch.name,
                branch.address,
                branch.rating,
                branch.review_count,
                branch.maps_url,
                branch.place_id,
                now,
            ),
        )
        await self._conn.commit()
        cursor = await self._conn.execute(
            """
            SELECT id FROM branches
            WHERE company_id = ? AND name = ? AND address = ?
            """,
            (company_id, branch.name, branch.address),
        )
        row = await cursor.fetchone()
        assert row is not None
        return int(row["id"])

    async def upsert_review(self, branch_id: int, review: Review) -> None:
        assert self._conn is not None
        now = datetime.now(timezone.utc).isoformat()
        external_id = review.external_id or f"{review.author}|{review.published_at}|{review.text[:80]}"
        await self._conn.execute(
            """
            INSERT INTO reviews (
                branch_id, author, rating, text, published_at, language,
                source, external_id, raw_json, collected_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(branch_id, external_id) DO UPDATE SET
                author = excluded.author,
                rating = excluded.rating,
                text = excluded.text,
                published_at = excluded.published_at,
                language = excluded.language,
                raw_json = excluded.raw_json,
                collected_at = excluded.collected_at
            """,
            (
                branch_id,
                review.author,
                review.rating,
                review.text,
                review.published_at,
                review.language,
                review.source,
                external_id,
                json.dumps(review.raw, ensure_ascii=False),
                now,
            ),
        )
        await self._conn.commit()

    async def stats(self) -> dict[str, int]:
        assert self._conn is not None
        result: dict[str, int] = {}
        for table in ("companies", "branches", "reviews"):
            cursor = await self._conn.execute(f"SELECT COUNT(*) AS c FROM {table}")
            row = await cursor.fetchone()
            result[table] = int(row["c"]) if row else 0
        return result
