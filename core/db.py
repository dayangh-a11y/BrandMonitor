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

            -- Phase 2.1: AI analysis foundation schema (refined contract)
            CREATE TABLE IF NOT EXISTS review_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id INTEGER NOT NULL UNIQUE,
                sentiment TEXT NOT NULL DEFAULT 'Neutral'
                    CHECK (sentiment IN ('Positive', 'Neutral', 'Negative')),
                complaint_categories TEXT NOT NULL DEFAULT '[]',
                positive_categories TEXT NOT NULL DEFAULT '[]',
                delivery_speed TEXT
                    CHECK (
                        delivery_speed IS NULL
                        OR delivery_speed IN ('fast', 'normal', 'slow')
                    ),
                customer_service TEXT
                    CHECK (
                        customer_service IS NULL
                        OR customer_service IN ('good', 'average', 'bad')
                    ),
                staff_behavior TEXT
                    CHECK (
                        staff_behavior IS NULL
                        OR staff_behavior IN ('good', 'average', 'bad')
                    ),
                package_damage INTEGER
                    CHECK (package_damage IS NULL OR package_damage IN (0, 1)),
                pricing TEXT
                    CHECK (
                        pricing IS NULL
                        OR pricing IN ('cheap', 'fair', 'expensive')
                    ),
                tracking TEXT
                    CHECK (
                        tracking IS NULL
                        OR tracking IN ('good', 'average', 'bad')
                    ),
                professionalism TEXT
                    CHECK (
                        professionalism IS NULL
                        OR professionalism IN ('good', 'average', 'bad')
                    ),
                mentioned_employees TEXT NOT NULL DEFAULT '[]',
                mentioned_city TEXT,
                mentioned_branch TEXT,
                urgency TEXT NOT NULL DEFAULT 'low'
                    CHECK (urgency IN ('low', 'medium', 'high')),
                evidence_spans TEXT NOT NULL DEFAULT '{}',
                confidence_overall REAL NOT NULL DEFAULT 0
                    CHECK (confidence_overall >= 0.0 AND confidence_overall <= 1.0),
                confidence_by_field TEXT NOT NULL DEFAULT '{}',
                language TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'succeeded', 'failed', 'skipped')),
                error TEXT,
                provider TEXT NOT NULL DEFAULT '',
                model_id TEXT NOT NULL DEFAULT '',
                prompt_version TEXT NOT NULL DEFAULT '',
                schema_version TEXT NOT NULL DEFAULT '',
                input_hash TEXT NOT NULL DEFAULT '',
                raw_response TEXT NOT NULL DEFAULT '{}',
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
            CREATE INDEX IF NOT EXISTS idx_review_analyses_input_hash
                ON review_analyses(input_hash);
            CREATE INDEX IF NOT EXISTS idx_analysis_jobs_status
                ON analysis_jobs(status);
            CREATE INDEX IF NOT EXISTS idx_branch_scores_branch_calculated
                ON branch_scores(branch_id, calculated_at);
            CREATE INDEX IF NOT EXISTS idx_company_scores_company_calculated
                ON company_scores(company_id, calculated_at);
            """
        )
        await self._conn.commit()
        await self._ensure_phase21_review_analyses_schema()

    async def _ensure_phase21_review_analyses_schema(self) -> None:
        """Upgrade legacy review_analyses shape if an older draft table exists."""
        assert self._conn is not None
        cursor = await self._conn.execute("PRAGMA table_info(review_analyses)")
        cols = {row["name"] for row in await cursor.fetchall()}
        if not cols:
            return
        if "complaint_categories" in cols and "input_hash" in cols and "staff_behavior" in cols:
            return

        await self._conn.execute("ALTER TABLE review_analyses RENAME TO review_analyses_legacy")
        await self._conn.executescript(
            """
            CREATE TABLE review_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id INTEGER NOT NULL UNIQUE,
                sentiment TEXT NOT NULL DEFAULT 'Neutral'
                    CHECK (sentiment IN ('Positive', 'Neutral', 'Negative')),
                complaint_categories TEXT NOT NULL DEFAULT '[]',
                positive_categories TEXT NOT NULL DEFAULT '[]',
                delivery_speed TEXT
                    CHECK (
                        delivery_speed IS NULL
                        OR delivery_speed IN ('fast', 'normal', 'slow')
                    ),
                customer_service TEXT
                    CHECK (
                        customer_service IS NULL
                        OR customer_service IN ('good', 'average', 'bad')
                    ),
                staff_behavior TEXT
                    CHECK (
                        staff_behavior IS NULL
                        OR staff_behavior IN ('good', 'average', 'bad')
                    ),
                package_damage INTEGER
                    CHECK (package_damage IS NULL OR package_damage IN (0, 1)),
                pricing TEXT
                    CHECK (
                        pricing IS NULL
                        OR pricing IN ('cheap', 'fair', 'expensive')
                    ),
                tracking TEXT
                    CHECK (
                        tracking IS NULL
                        OR tracking IN ('good', 'average', 'bad')
                    ),
                professionalism TEXT
                    CHECK (
                        professionalism IS NULL
                        OR professionalism IN ('good', 'average', 'bad')
                    ),
                mentioned_employees TEXT NOT NULL DEFAULT '[]',
                mentioned_city TEXT,
                mentioned_branch TEXT,
                urgency TEXT NOT NULL DEFAULT 'low'
                    CHECK (urgency IN ('low', 'medium', 'high')),
                evidence_spans TEXT NOT NULL DEFAULT '{}',
                confidence_overall REAL NOT NULL DEFAULT 0
                    CHECK (confidence_overall >= 0.0 AND confidence_overall <= 1.0),
                confidence_by_field TEXT NOT NULL DEFAULT '{}',
                language TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'succeeded', 'failed', 'skipped')),
                error TEXT,
                provider TEXT NOT NULL DEFAULT '',
                model_id TEXT NOT NULL DEFAULT '',
                prompt_version TEXT NOT NULL DEFAULT '',
                schema_version TEXT NOT NULL DEFAULT '',
                input_hash TEXT NOT NULL DEFAULT '',
                raw_response TEXT NOT NULL DEFAULT '{}',
                analyzed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(review_id) REFERENCES reviews(id)
            );
            CREATE INDEX IF NOT EXISTS idx_review_analyses_status ON review_analyses(status);
            CREATE INDEX IF NOT EXISTS idx_review_analyses_sentiment ON review_analyses(sentiment);
            CREATE INDEX IF NOT EXISTS idx_review_analyses_input_hash ON review_analyses(input_hash);
            DROP TABLE IF EXISTS review_analyses_legacy;
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

    async def upsert_review(self, branch_id: int, review: Review) -> int:
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
        cursor = await self._conn.execute(
            """
            SELECT id FROM reviews
            WHERE branch_id = ? AND external_id = ?
            """,
            (branch_id, external_id),
        )
        row = await cursor.fetchone()
        assert row is not None
        return int(row["id"])

    async def get_review_row(self, review_id: int):
        assert self._conn is not None
        cursor = await self._conn.execute(
            """
            SELECT
                r.*,
                b.name AS branch_name
            FROM reviews r
            JOIN branches b ON b.id = r.branch_id
            WHERE r.id = ?
            """,
            (review_id,),
        )
        return await cursor.fetchone()

    async def create_analysis_job(
        self,
        *,
        scope: str,
        scope_id: int | None,
        total_items: int = 1,
    ) -> int:
        assert self._conn is not None
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self._conn.execute(
            """
            INSERT INTO analysis_jobs (
                scope, scope_id, status, total_items, done_items, failed_items, created_at
            ) VALUES (?, ?, 'queued', ?, 0, 0, ?)
            """,
            (scope, scope_id, total_items, now),
        )
        await self._conn.commit()
        return int(cursor.lastrowid)

    async def claim_next_analysis_job(self):
        assert self._conn is not None
        cursor = await self._conn.execute(
            """
            SELECT * FROM analysis_jobs
            WHERE status = 'queued'
            ORDER BY id ASC
            LIMIT 1
            """
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """
            UPDATE analysis_jobs
            SET status = 'running', started_at = ?
            WHERE id = ? AND status = 'queued'
            """,
            (now, row["id"]),
        )
        await self._conn.commit()
        cursor = await self._conn.execute(
            "SELECT * FROM analysis_jobs WHERE id = ?",
            (row["id"],),
        )
        return await cursor.fetchone()

    async def finish_analysis_job(
        self,
        job_id: int,
        *,
        status: str,
        done_items: int,
        failed_items: int,
        error: str | None = None,
    ) -> None:
        assert self._conn is not None
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """
            UPDATE analysis_jobs
            SET status = ?, done_items = ?, failed_items = ?, error = ?, finished_at = ?
            WHERE id = ?
            """,
            (status, done_items, failed_items, error, now, job_id),
        )
        await self._conn.commit()

    async def upsert_review_analysis(
        self,
        review_id: int,
        analysis,
        *,
        input_hash: str,
    ) -> None:
        from models.analysis import AnalysisDTO

        assert self._conn is not None
        assert isinstance(analysis, AnalysisDTO)
        now = datetime.now(timezone.utc).isoformat()
        analyzed_at = now if analysis.status in {"succeeded", "skipped"} else None
        await self._conn.execute(
            """
            INSERT INTO review_analyses (
                review_id, sentiment, complaint_categories, positive_categories,
                delivery_speed, customer_service, staff_behavior, package_damage,
                pricing, tracking, professionalism, mentioned_employees,
                mentioned_city, mentioned_branch, urgency, evidence_spans,
                confidence_overall, confidence_by_field, language, status, error,
                provider, model_id, prompt_version, schema_version, input_hash,
                raw_response, analyzed_at, created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(review_id) DO UPDATE SET
                sentiment = excluded.sentiment,
                complaint_categories = excluded.complaint_categories,
                positive_categories = excluded.positive_categories,
                delivery_speed = excluded.delivery_speed,
                customer_service = excluded.customer_service,
                staff_behavior = excluded.staff_behavior,
                package_damage = excluded.package_damage,
                pricing = excluded.pricing,
                tracking = excluded.tracking,
                professionalism = excluded.professionalism,
                mentioned_employees = excluded.mentioned_employees,
                mentioned_city = excluded.mentioned_city,
                mentioned_branch = excluded.mentioned_branch,
                urgency = excluded.urgency,
                evidence_spans = excluded.evidence_spans,
                confidence_overall = excluded.confidence_overall,
                confidence_by_field = excluded.confidence_by_field,
                language = excluded.language,
                status = excluded.status,
                error = excluded.error,
                provider = excluded.provider,
                model_id = excluded.model_id,
                prompt_version = excluded.prompt_version,
                schema_version = excluded.schema_version,
                input_hash = excluded.input_hash,
                raw_response = excluded.raw_response,
                analyzed_at = excluded.analyzed_at,
                updated_at = excluded.updated_at
            """,
            (
                review_id,
                analysis.sentiment,
                json.dumps(analysis.complaint_categories, ensure_ascii=False),
                json.dumps(analysis.positive_categories, ensure_ascii=False),
                analysis.delivery_speed,
                analysis.customer_service,
                analysis.staff_behavior,
                None if analysis.package_damage is None else int(analysis.package_damage),
                analysis.pricing,
                analysis.tracking,
                analysis.professionalism,
                json.dumps(analysis.mentioned_employees, ensure_ascii=False),
                analysis.mentioned_city,
                analysis.mentioned_branch,
                analysis.urgency,
                json.dumps(analysis.evidence_spans, ensure_ascii=False),
                analysis.confidence_overall,
                json.dumps(analysis.confidence_by_field.model_dump(), ensure_ascii=False),
                analysis.language,
                analysis.status,
                analysis.error,
                analysis.provider,
                analysis.model_id,
                analysis.prompt_version,
                analysis.schema_version,
                input_hash,
                json.dumps(analysis.raw_response, ensure_ascii=False),
                analyzed_at,
                now,
                now,
            ),
        )
        await self._conn.commit()

    async def get_analysis_input_hash(self, review_id: int) -> str | None:
        assert self._conn is not None
        cursor = await self._conn.execute(
            "SELECT input_hash, status FROM review_analyses WHERE review_id = ?",
            (review_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        if row["status"] not in {"succeeded", "skipped"}:
            return None
        return row["input_hash"] or None

    async def get_analysis_dto(self, review_id: int):
        from models.analysis import AnalysisDTO, ConfidenceByField

        assert self._conn is not None
        cursor = await self._conn.execute(
            "SELECT * FROM review_analyses WHERE review_id = ?",
            (review_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        package_damage = row["package_damage"]
        return AnalysisDTO(
            sentiment=row["sentiment"],
            complaint_categories=json.loads(row["complaint_categories"] or "[]"),
            positive_categories=json.loads(row["positive_categories"] or "[]"),
            delivery_speed=row["delivery_speed"],
            customer_service=row["customer_service"],
            staff_behavior=row["staff_behavior"],
            package_damage=None if package_damage is None else bool(package_damage),
            pricing=row["pricing"],
            tracking=row["tracking"],
            professionalism=row["professionalism"],
            mentioned_employees=json.loads(row["mentioned_employees"] or "[]"),
            mentioned_city=row["mentioned_city"],
            mentioned_branch=row["mentioned_branch"],
            urgency=row["urgency"],
            evidence_spans=json.loads(row["evidence_spans"] or "{}"),
            confidence_overall=float(row["confidence_overall"] or 0),
            confidence_by_field=ConfidenceByField.model_validate(
                json.loads(row["confidence_by_field"] or "{}")
            ),
            language=row["language"],
            status=row["status"],
            error=row["error"],
            provider=row["provider"] or "",
            model_id=row["model_id"] or "",
            prompt_version=row["prompt_version"] or "",
            schema_version=row["schema_version"] or "",
            raw_response=json.loads(row["raw_response"] or "{}"),
        )

    async def stats(self) -> dict[str, int]:
        assert self._conn is not None
        result: dict[str, int] = {}
        for table in ("companies", "branches", "reviews", "review_analyses", "analysis_jobs"):
            cursor = await self._conn.execute(f"SELECT COUNT(*) AS c FROM {table}")
            row = await cursor.fetchone()
            result[table] = int(row["c"]) if row else 0
        return result

    async def list_companies(
        self,
        *,
        sort: str = "newest",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        assert self._conn is not None
        order_sql = {
            "newest": "c.created_at DESC, c.id DESC",
            "oldest": "c.created_at ASC, c.id ASC",
            "highest_score": "latest_score IS NULL, latest_score DESC, c.id DESC",
            "lowest_score": "latest_score IS NULL, latest_score ASC, c.id DESC",
        }.get(sort, "c.created_at DESC, c.id DESC")
        cursor = await self._conn.execute(
            f"""
            SELECT
                c.id, c.name, c.source, c.created_at,
                COUNT(DISTINCT b.id) AS branch_count,
                COUNT(DISTINCT r.id) AS review_count,
                (
                    SELECT cs.score
                    FROM company_scores cs
                    WHERE cs.company_id = c.id
                    ORDER BY cs.calculated_at DESC, cs.id DESC
                    LIMIT 1
                ) AS latest_score
            FROM companies c
            LEFT JOIN branches b ON b.company_id = c.id
            LEFT JOIN reviews r ON r.branch_id = b.id
            GROUP BY c.id
            ORDER BY {order_sql}
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def get_company(self, company_id: int) -> dict | None:
        assert self._conn is not None
        cursor = await self._conn.execute(
            """
            SELECT
                c.id, c.name, c.source, c.created_at,
                COUNT(DISTINCT b.id) AS branch_count,
                COUNT(DISTINCT r.id) AS review_count,
                (
                    SELECT cs.score
                    FROM company_scores cs
                    WHERE cs.company_id = c.id
                    ORDER BY cs.calculated_at DESC, cs.id DESC
                    LIMIT 1
                ) AS latest_score
            FROM companies c
            LEFT JOIN branches b ON b.company_id = c.id
            LEFT JOIN reviews r ON r.branch_id = b.id
            WHERE c.id = ?
            GROUP BY c.id
            """,
            (company_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_company_branches(
        self,
        company_id: int,
        *,
        sort: str = "newest",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        assert self._conn is not None
        order_sql = {
            "newest": "b.collected_at DESC, b.id DESC",
            "oldest": "b.collected_at ASC, b.id ASC",
            "highest_score": "latest_score IS NULL, latest_score DESC, b.id DESC",
            "lowest_score": "latest_score IS NULL, latest_score ASC, b.id DESC",
        }.get(sort, "b.collected_at DESC, b.id DESC")
        cursor = await self._conn.execute(
            f"""
            SELECT
                b.*,
                c.name AS company_name,
                (
                    SELECT bs.score
                    FROM branch_scores bs
                    WHERE bs.branch_id = b.id
                    ORDER BY bs.calculated_at DESC, bs.id DESC
                    LIMIT 1
                ) AS latest_score
            FROM branches b
            JOIN companies c ON c.id = b.company_id
            WHERE b.company_id = ?
            ORDER BY {order_sql}
            LIMIT ? OFFSET ?
            """,
            (company_id, limit, offset),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def get_branch(self, branch_id: int) -> dict | None:
        assert self._conn is not None
        cursor = await self._conn.execute(
            """
            SELECT
                b.*,
                c.name AS company_name,
                (
                    SELECT bs.score
                    FROM branch_scores bs
                    WHERE bs.branch_id = b.id
                    ORDER BY bs.calculated_at DESC, bs.id DESC
                    LIMIT 1
                ) AS latest_score
            FROM branches b
            JOIN companies c ON c.id = b.company_id
            WHERE b.id = ?
            """,
            (branch_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_branch_reviews(
        self,
        branch_id: int,
        *,
        limit: int = 20,
        offset: int = 0,
        sentiment: str | None = None,
        category: str | None = None,
        city: str | None = None,
        sort: str = "newest",
    ) -> tuple[list[dict], int]:
        assert self._conn is not None
        where = ["r.branch_id = ?"]
        params: list[object] = [branch_id]

        if sentiment:
            where.append("LOWER(ra.sentiment) = LOWER(?)")
            params.append(sentiment)
        if category:
            where.append(
                "(ra.complaint_categories LIKE ? OR ra.positive_categories LIKE ?)"
            )
            like = f'%"{category}"%'
            params.extend([like, like])
        if city:
            where.append("LOWER(COALESCE(ra.mentioned_city, '')) LIKE LOWER(?)")
            params.append(f"%{city}%")

        where_sql = " AND ".join(where)
        order_sql = {
            "newest": "r.collected_at DESC, r.id DESC",
            "oldest": "r.collected_at ASC, r.id ASC",
            "highest_score": "r.rating DESC, r.id DESC",
            "lowest_score": "r.rating ASC, r.id DESC",
        }.get(sort, "r.collected_at DESC, r.id DESC")

        count_cursor = await self._conn.execute(
            f"""
            SELECT COUNT(*) AS c
            FROM reviews r
            LEFT JOIN review_analyses ra ON ra.review_id = r.id
            WHERE {where_sql}
            """,
            params,
        )
        total_row = await count_cursor.fetchone()
        total = int(total_row["c"]) if total_row else 0

        cursor = await self._conn.execute(
            f"""
            SELECT
                r.id, r.branch_id, r.author, r.rating, r.text, r.published_at,
                r.language, r.source, r.external_id, r.collected_at,
                ra.sentiment,
                ra.complaint_categories,
                ra.positive_categories,
                ra.mentioned_city
            FROM reviews r
            LEFT JOIN review_analyses ra ON ra.review_id = r.id
            WHERE {where_sql}
            ORDER BY {order_sql}
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        )
        rows = []
        for row in await cursor.fetchall():
            item = dict(row)
            item["complaint_categories"] = json.loads(item.pop("complaint_categories") or "[]")
            item["positive_categories"] = json.loads(item.pop("positive_categories") or "[]")
            rows.append(item)
        return rows, total

    async def get_branch_score(self, branch_id: int) -> dict | None:
        assert self._conn is not None
        cursor = await self._conn.execute(
            """
            SELECT *
            FROM branch_scores
            WHERE branch_id = ?
            ORDER BY calculated_at DESC, id DESC
            LIMIT 1
            """,
            (branch_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        data = dict(row)
        data["components"] = json.loads(data.get("components") or "{}")
        return data

    async def get_company_score(self, company_id: int) -> dict | None:
        assert self._conn is not None
        cursor = await self._conn.execute(
            """
            SELECT *
            FROM company_scores
            WHERE company_id = ?
            ORDER BY calculated_at DESC, id DESC
            LIMIT 1
            """,
            (company_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        data = dict(row)
        data["components"] = json.loads(data.get("components") or "{}")
        return data

    async def get_company_insights(self, company_id: int) -> dict | None:
        assert self._conn is not None
        cursor = await self._conn.execute(
            "SELECT * FROM company_insights WHERE company_id = ?",
            (company_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        data = dict(row)
        data["pros"] = json.loads(data.get("pros") or "[]")
        data["cons"] = json.loads(data.get("cons") or "[]")
        data["common_categories"] = json.loads(data.get("common_categories") or "[]")
        return data

    async def get_branch_insights(self, branch_id: int) -> dict | None:
        assert self._conn is not None
        cursor = await self._conn.execute(
            "SELECT * FROM branch_insights WHERE branch_id = ?",
            (branch_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        data = dict(row)
        data["pros"] = json.loads(data.get("pros") or "[]")
        data["cons"] = json.loads(data.get("cons") or "[]")
        data["common_categories"] = json.loads(data.get("common_categories") or "[]")
        return data

    async def upsert_company_insights(
        self,
        company_id: int,
        *,
        summary: str,
        pros: list[str],
        cons: list[str],
        common_categories: list[str],
        review_count_used: int,
        model_name: str = "demo",
        prompt_version: str = "demo_v1",
    ) -> None:
        assert self._conn is not None
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """
            INSERT INTO company_insights (
                company_id, summary, pros, cons, common_categories,
                review_count_used, model_name, prompt_version, generated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company_id) DO UPDATE SET
                summary = excluded.summary,
                pros = excluded.pros,
                cons = excluded.cons,
                common_categories = excluded.common_categories,
                review_count_used = excluded.review_count_used,
                model_name = excluded.model_name,
                prompt_version = excluded.prompt_version,
                generated_at = excluded.generated_at
            """,
            (
                company_id,
                summary,
                json.dumps(pros, ensure_ascii=False),
                json.dumps(cons, ensure_ascii=False),
                json.dumps(common_categories, ensure_ascii=False),
                review_count_used,
                model_name,
                prompt_version,
                now,
            ),
        )
        await self._conn.commit()

    async def upsert_branch_insights(
        self,
        branch_id: int,
        *,
        summary: str,
        pros: list[str],
        cons: list[str],
        common_categories: list[str],
        review_count_used: int,
        model_name: str = "demo",
        prompt_version: str = "demo_v1",
    ) -> None:
        assert self._conn is not None
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """
            INSERT INTO branch_insights (
                branch_id, summary, pros, cons, common_categories,
                review_count_used, model_name, prompt_version, generated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(branch_id) DO UPDATE SET
                summary = excluded.summary,
                pros = excluded.pros,
                cons = excluded.cons,
                common_categories = excluded.common_categories,
                review_count_used = excluded.review_count_used,
                model_name = excluded.model_name,
                prompt_version = excluded.prompt_version,
                generated_at = excluded.generated_at
            """,
            (
                branch_id,
                summary,
                json.dumps(pros, ensure_ascii=False),
                json.dumps(cons, ensure_ascii=False),
                json.dumps(common_categories, ensure_ascii=False),
                review_count_used,
                model_name,
                prompt_version,
                now,
            ),
        )
        await self._conn.commit()

    async def insert_branch_score(
        self,
        branch_id: int,
        *,
        score: float,
        components: dict,
        algorithm_version: str = "score_v1",
    ) -> None:
        assert self._conn is not None
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """
            INSERT INTO branch_scores (
                branch_id, score, components, algorithm_version, calculated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (branch_id, score, json.dumps(components, ensure_ascii=False), algorithm_version, now),
        )
        await self._conn.commit()

    async def insert_company_score(
        self,
        company_id: int,
        *,
        score: float,
        components: dict,
        algorithm_version: str = "score_v1",
    ) -> None:
        assert self._conn is not None
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """
            INSERT INTO company_scores (
                company_id, score, components, algorithm_version, calculated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (company_id, score, json.dumps(components, ensure_ascii=False), algorithm_version, now),
        )
        await self._conn.commit()

    async def search(
        self,
        query: str,
        *,
        limit: int = 20,
        sort: str = "newest",
    ) -> dict[str, list[dict]]:
        assert self._conn is not None
        q = f"%{query.strip()}%"
        company_order = {
            "newest": "c.created_at DESC",
            "oldest": "c.created_at ASC",
            "highest_score": "latest_score IS NULL, latest_score DESC",
            "lowest_score": "latest_score IS NULL, latest_score ASC",
        }.get(sort, "c.created_at DESC")
        branch_order = {
            "newest": "b.collected_at DESC",
            "oldest": "b.collected_at ASC",
            "highest_score": "latest_score IS NULL, latest_score DESC",
            "lowest_score": "latest_score IS NULL, latest_score ASC",
        }.get(sort, "b.collected_at DESC")

        companies_cursor = await self._conn.execute(
            f"""
            SELECT
                c.id, c.name, c.source, c.created_at,
                COUNT(DISTINCT b.id) AS branch_count,
                COUNT(DISTINCT r.id) AS review_count,
                (
                    SELECT cs.score FROM company_scores cs
                    WHERE cs.company_id = c.id
                    ORDER BY cs.calculated_at DESC, cs.id DESC LIMIT 1
                ) AS latest_score
            FROM companies c
            LEFT JOIN branches b ON b.company_id = c.id
            LEFT JOIN reviews r ON r.branch_id = b.id
            WHERE c.name LIKE ?
            GROUP BY c.id
            ORDER BY {company_order}
            LIMIT ?
            """,
            (q, limit),
        )
        branches_cursor = await self._conn.execute(
            f"""
            SELECT
                b.*,
                c.name AS company_name,
                (
                    SELECT bs.score FROM branch_scores bs
                    WHERE bs.branch_id = b.id
                    ORDER BY bs.calculated_at DESC, bs.id DESC LIMIT 1
                ) AS latest_score
            FROM branches b
            JOIN companies c ON c.id = b.company_id
            WHERE b.name LIKE ? OR b.address LIKE ? OR c.name LIKE ?
            ORDER BY {branch_order}
            LIMIT ?
            """,
            (q, q, q, limit),
        )
        return {
            "companies": [dict(row) for row in await companies_cursor.fetchall()],
            "branches": [dict(row) for row in await branches_cursor.fetchall()],
        }
