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

            -- Phase 4: production crawl pipeline
            CREATE TABLE IF NOT EXISTS crawl_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'full'
                    CHECK (mode IN ('full', 'incremental')),
                status TEXT NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'interrupted')),
                config_json TEXT NOT NULL DEFAULT '{}',
                error TEXT,
                started_at TEXT,
                finished_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS crawl_branch_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                branch_id INTEGER,
                place_id TEXT NOT NULL DEFAULT '',
                branch_name TEXT NOT NULL DEFAULT '',
                address TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'skipped', 'deleted')),
                attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 3,
                last_error TEXT,
                reviews_found INTEGER NOT NULL DEFAULT 0,
                reviews_new INTEGER NOT NULL DEFAULT 0,
                reviews_updated INTEGER NOT NULL DEFAULT 0,
                discovered_at TEXT,
                started_at TEXT,
                completed_at TEXT,
                FOREIGN KEY(run_id) REFERENCES crawl_runs(id),
                FOREIGN KEY(branch_id) REFERENCES branches(id)
            );

            CREATE TABLE IF NOT EXISTS crawl_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                metric TEXT NOT NULL,
                value REAL NOT NULL DEFAULT 0,
                recorded_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES crawl_runs(id)
            );

            CREATE TABLE IF NOT EXISTS crawl_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL UNIQUE,
                report_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES crawl_runs(id)
            );

            CREATE TABLE IF NOT EXISTS crawl_checkpoints (
                run_id INTEGER PRIMARY KEY,
                cursor_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES crawl_runs(id)
            );

            CREATE INDEX IF NOT EXISTS idx_crawl_runs_status ON crawl_runs(status);
            CREATE INDEX IF NOT EXISTS idx_crawl_branch_tasks_run_status
                ON crawl_branch_tasks(run_id, status);
            CREATE INDEX IF NOT EXISTS idx_crawl_stats_run_metric
                ON crawl_stats(run_id, metric);
            """
        )
        await self._conn.commit()
        await self._ensure_phase21_review_analyses_schema()
        await self._ensure_phase4_branch_soft_delete_columns()
        await self._ensure_phase6_collection_columns()
        await self._ensure_ops_metric_samples()

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

    async def _ensure_phase4_branch_soft_delete_columns(self) -> None:
        assert self._conn is not None
        cursor = await self._conn.execute("PRAGMA table_info(branches)")
        cols = {row["name"] for row in await cursor.fetchall()}
        if "is_deleted" not in cols:
            await self._conn.execute(
                "ALTER TABLE branches ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0"
            )
        if "last_seen_at" not in cols:
            await self._conn.execute("ALTER TABLE branches ADD COLUMN last_seen_at TEXT")
        await self._conn.commit()

    async def _ensure_phase6_collection_columns(self) -> None:
        """Add branch metadata + review owner/deleted/hash columns for production collection."""
        assert self._conn is not None
        cursor = await self._conn.execute("PRAGMA table_info(branches)")
        branch_cols = {row["name"] for row in await cursor.fetchall()}
        branch_alters = {
            "phone": "ALTER TABLE branches ADD COLUMN phone TEXT NOT NULL DEFAULT ''",
            "latitude": "ALTER TABLE branches ADD COLUMN latitude REAL",
            "longitude": "ALTER TABLE branches ADD COLUMN longitude REAL",
            "city": "ALTER TABLE branches ADD COLUMN city TEXT NOT NULL DEFAULT ''",
            "province": "ALTER TABLE branches ADD COLUMN province TEXT NOT NULL DEFAULT ''",
            "metadata_json": "ALTER TABLE branches ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'",
            "last_success_at": "ALTER TABLE branches ADD COLUMN last_success_at TEXT",
        }
        for col, sql in branch_alters.items():
            if col not in branch_cols:
                await self._conn.execute(sql)

        cursor = await self._conn.execute("PRAGMA table_info(reviews)")
        review_cols = {row["name"] for row in await cursor.fetchall()}
        review_alters = {
            "owner_response": "ALTER TABLE reviews ADD COLUMN owner_response TEXT NOT NULL DEFAULT ''",
            "owner_response_at": "ALTER TABLE reviews ADD COLUMN owner_response_at TEXT NOT NULL DEFAULT ''",
            "is_deleted": "ALTER TABLE reviews ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0",
            "content_hash": "ALTER TABLE reviews ADD COLUMN content_hash TEXT NOT NULL DEFAULT ''",
            "last_seen_at": "ALTER TABLE reviews ADD COLUMN last_seen_at TEXT",
        }
        for col, sql in review_alters.items():
            if col not in review_cols:
                await self._conn.execute(sql)
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reviews_branch_deleted ON reviews(branch_id, is_deleted)"
        )
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reviews_content_hash ON reviews(branch_id, content_hash)"
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
                maps_url, place_id, collected_at,
                phone, latitude, longitude, city, province, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company_id, name, address) DO UPDATE SET
                rating = excluded.rating,
                review_count = excluded.review_count,
                maps_url = excluded.maps_url,
                place_id = excluded.place_id,
                collected_at = excluded.collected_at,
                phone = excluded.phone,
                latitude = excluded.latitude,
                longitude = excluded.longitude,
                city = excluded.city,
                province = excluded.province,
                metadata_json = excluded.metadata_json,
                is_deleted = 0
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
                branch.phone or "",
                branch.latitude,
                branch.longitude,
                branch.city or "",
                branch.province or "",
                json.dumps(branch.metadata or {}, ensure_ascii=False),
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
        content_hash = review.content_hash or ""
        if not content_hash:
            from collectors.dedupe import review_content_hash

            content_hash = review_content_hash(review)
        await self._conn.execute(
            """
            INSERT INTO reviews (
                branch_id, author, rating, text, published_at, language,
                source, external_id, raw_json, collected_at,
                owner_response, owner_response_at, is_deleted, content_hash, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            ON CONFLICT(branch_id, external_id) DO UPDATE SET
                author = excluded.author,
                rating = excluded.rating,
                text = excluded.text,
                published_at = excluded.published_at,
                language = excluded.language,
                raw_json = excluded.raw_json,
                collected_at = excluded.collected_at,
                owner_response = excluded.owner_response,
                owner_response_at = excluded.owner_response_at,
                is_deleted = 0,
                content_hash = excluded.content_hash,
                last_seen_at = excluded.last_seen_at
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
                review.owner_response or "",
                review.owner_response_at or "",
                content_hash,
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

    async def list_branch_analyses(self, branch_id: int) -> list[dict]:
        """Return analysis rows joined to reviews for scoring/insights."""
        assert self._conn is not None
        cursor = await self._conn.execute(
            """
            SELECT
                a.*,
                r.branch_id,
                r.rating AS review_rating,
                r.text AS review_text
            FROM review_analyses a
            JOIN reviews r ON r.id = a.review_id
            WHERE r.branch_id = ?
            ORDER BY a.id ASC
            """,
            (branch_id,),
        )
        rows = []
        for row in await cursor.fetchall():
            item = dict(row)
            item["complaint_categories"] = json.loads(item.get("complaint_categories") or "[]")
            item["positive_categories"] = json.loads(item.get("positive_categories") or "[]")
            item["mentioned_employees"] = json.loads(item.get("mentioned_employees") or "[]")
            item["evidence_spans"] = json.loads(item.get("evidence_spans") or "{}")
            item["confidence_by_field"] = json.loads(item.get("confidence_by_field") or "{}")
            if item.get("package_damage") is not None:
                item["package_damage"] = bool(item["package_damage"])
            rows.append(item)
        return rows

    async def list_pending_review_ids(self, *, limit: int = 200) -> list[int]:
        assert self._conn is not None
        cursor = await self._conn.execute(
            """
            SELECT r.id
            FROM reviews r
            LEFT JOIN review_analyses a ON a.review_id = r.id
            WHERE a.review_id IS NULL
               OR a.status IN ('failed', 'pending')
            ORDER BY r.id ASC
            LIMIT ?
            """,
            (max(1, min(int(limit), 100000)),),
        )
        return [int(row["id"]) for row in await cursor.fetchall()]

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

    # --- Phase 4 crawl persistence ---

    async def create_crawl_run(
        self,
        *,
        company_name: str,
        mode: str = "full",
        config: dict | None = None,
    ) -> int:
        assert self._conn is not None
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self._conn.execute(
            """
            INSERT INTO crawl_runs (company_name, mode, status, config_json, created_at)
            VALUES (?, ?, 'queued', ?, ?)
            """,
            (company_name, mode, json.dumps(config or {}, ensure_ascii=False), now),
        )
        await self._conn.commit()
        return int(cursor.lastrowid)

    async def update_crawl_run_status(
        self,
        run_id: int,
        status: str,
        *,
        error: str | None = None,
        started: bool = False,
        finished: bool = False,
    ) -> None:
        assert self._conn is not None
        now = datetime.now(timezone.utc).isoformat()
        fields = ["status = ?"]
        params: list[object] = [status]
        if error is not None:
            fields.append("error = ?")
            params.append(error)
        if started:
            fields.append("started_at = COALESCE(started_at, ?)")
            params.append(now)
        if finished:
            fields.append("finished_at = ?")
            params.append(now)
        params.append(run_id)
        await self._conn.execute(
            f"UPDATE crawl_runs SET {', '.join(fields)} WHERE id = ?",
            params,
        )
        await self._conn.commit()

    async def get_crawl_run(self, run_id: int) -> dict | None:
        assert self._conn is not None
        cursor = await self._conn.execute("SELECT * FROM crawl_runs WHERE id = ?", (run_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def add_crawl_branch_task(
        self,
        run_id: int,
        *,
        branch_name: str,
        address: str = "",
        place_id: str = "",
        branch_id: int | None = None,
        max_attempts: int = 3,
    ) -> int:
        assert self._conn is not None
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self._conn.execute(
            """
            INSERT INTO crawl_branch_tasks (
                run_id, branch_id, place_id, branch_name, address,
                status, max_attempts, discovered_at
            ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (run_id, branch_id, place_id, branch_name, address, max_attempts, now),
        )
        await self._conn.commit()
        return int(cursor.lastrowid)

    async def list_crawl_branch_tasks(
        self,
        run_id: int,
        *,
        statuses: list[str] | None = None,
    ) -> list[dict]:
        assert self._conn is not None
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            cursor = await self._conn.execute(
                f"""
                SELECT * FROM crawl_branch_tasks
                WHERE run_id = ? AND status IN ({placeholders})
                ORDER BY id ASC
                """,
                (run_id, *statuses),
            )
        else:
            cursor = await self._conn.execute(
                "SELECT * FROM crawl_branch_tasks WHERE run_id = ? ORDER BY id ASC",
                (run_id,),
            )
        return [dict(row) for row in await cursor.fetchall()]

    async def claim_next_branch_task(self, run_id: int) -> dict | None:
        assert self._conn is not None
        cursor = await self._conn.execute(
            """
            SELECT * FROM crawl_branch_tasks
            WHERE run_id = ? AND status IN ('pending', 'failed')
              AND attempts < max_attempts
            ORDER BY
              CASE status WHEN 'pending' THEN 0 ELSE 1 END,
              id ASC
            LIMIT 1
            """,
            (run_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """
            UPDATE crawl_branch_tasks
            SET status = 'running',
                attempts = attempts + 1,
                started_at = COALESCE(started_at, ?),
                last_error = NULL
            WHERE id = ?
            """,
            (now, row["id"]),
        )
        await self._conn.commit()
        cursor = await self._conn.execute(
            "SELECT * FROM crawl_branch_tasks WHERE id = ?",
            (row["id"],),
        )
        claimed = await cursor.fetchone()
        return dict(claimed) if claimed else None

    async def finish_branch_task(
        self,
        task_id: int,
        *,
        status: str,
        branch_id: int | None = None,
        reviews_found: int = 0,
        reviews_new: int = 0,
        reviews_updated: int = 0,
        error: str | None = None,
    ) -> None:
        assert self._conn is not None
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """
            UPDATE crawl_branch_tasks
            SET status = ?,
                branch_id = COALESCE(?, branch_id),
                reviews_found = ?,
                reviews_new = ?,
                reviews_updated = ?,
                last_error = ?,
                completed_at = ?
            WHERE id = ?
            """,
            (
                status,
                branch_id,
                reviews_found,
                reviews_new,
                reviews_updated,
                error,
                now,
                task_id,
            ),
        )
        await self._conn.commit()

    async def save_checkpoint(self, run_id: int, cursor_data: dict) -> None:
        assert self._conn is not None
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """
            INSERT INTO crawl_checkpoints (run_id, cursor_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                cursor_json = excluded.cursor_json,
                updated_at = excluded.updated_at
            """,
            (run_id, json.dumps(cursor_data, ensure_ascii=False), now),
        )
        await self._conn.commit()

    async def get_checkpoint(self, run_id: int) -> dict:
        assert self._conn is not None
        cursor = await self._conn.execute(
            "SELECT cursor_json FROM crawl_checkpoints WHERE run_id = ?",
            (run_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return {}
        return json.loads(row["cursor_json"] or "{}")

    async def record_crawl_stat(self, run_id: int, metric: str, value: float) -> None:
        assert self._conn is not None
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """
            INSERT INTO crawl_stats (run_id, metric, value, recorded_at)
            VALUES (?, ?, ?, ?)
            """,
            (run_id, metric, value, now),
        )
        await self._conn.commit()

    async def get_crawl_stats(self, run_id: int) -> dict[str, float]:
        assert self._conn is not None
        cursor = await self._conn.execute(
            """
            SELECT metric, SUM(value) AS total
            FROM crawl_stats
            WHERE run_id = ?
            GROUP BY metric
            """,
            (run_id,),
        )
        return {row["metric"]: float(row["total"]) for row in await cursor.fetchall()}

    async def save_crawl_report(self, run_id: int, report: dict) -> None:
        assert self._conn is not None
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """
            INSERT INTO crawl_reports (run_id, report_json, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                report_json = excluded.report_json,
                created_at = excluded.created_at
            """,
            (run_id, json.dumps(report, ensure_ascii=False), now),
        )
        await self._conn.commit()

    async def get_crawl_report(self, run_id: int) -> dict | None:
        assert self._conn is not None
        cursor = await self._conn.execute(
            "SELECT report_json FROM crawl_reports WHERE run_id = ?",
            (run_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return json.loads(row["report_json"] or "{}")

    async def list_company_branch_rows(self, company_id: int) -> list[dict]:
        assert self._conn is not None
        cursor = await self._conn.execute(
            """
            SELECT * FROM branches
            WHERE company_id = ?
            ORDER BY id ASC
            """,
            (company_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def mark_branches_deleted(self, branch_ids: list[int]) -> None:
        if not branch_ids:
            return
        assert self._conn is not None
        placeholders = ",".join("?" for _ in branch_ids)
        await self._conn.execute(
            f"UPDATE branches SET is_deleted = 1 WHERE id IN ({placeholders})",
            branch_ids,
        )
        await self._conn.commit()

    async def mark_branch_seen(self, branch_id: int) -> None:
        assert self._conn is not None
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """
            UPDATE branches
            SET is_deleted = 0, last_seen_at = ?
            WHERE id = ?
            """,
            (now, branch_id),
        )
        await self._conn.commit()

    async def get_branch_known_review_keys(
        self, branch_id: int
    ) -> tuple[set[str], set[str], dict[str, str], list[dict]]:
        """
        Returns:
          known_external_ids, known_fingerprints, content_hash_by_key, active_rows
        key prefers external_id else fingerprint.
        """
        assert self._conn is not None
        cursor = await self._conn.execute(
            """
            SELECT id, external_id, author, published_at, text, rating, content_hash, is_deleted
            FROM reviews
            WHERE branch_id = ?
            """,
            (branch_id,),
        )
        external_ids: set[str] = set()
        fingerprints: set[str] = set()
        content_hash_by_key: dict[str, str] = {}
        active_rows: list[dict] = []
        from collectors.dedupe import review_fingerprint
        from models.review import Review

        for row in await cursor.fetchall():
            item = dict(row)
            external = (item.get("external_id") or "").strip()
            fp = review_fingerprint(
                Review(
                    author=item.get("author") or "",
                    published_at=item.get("published_at") or "",
                    text=item.get("text") or "",
                    rating=float(item.get("rating") or 0),
                    external_id=external,
                ),
                branch_key=str(branch_id),
            )
            if external:
                external_ids.add(external)
            fingerprints.add(fp)
            key = external or fp
            content_hash_by_key[key] = item.get("content_hash") or ""
            if not int(item.get("is_deleted") or 0):
                active_rows.append({**item, "fingerprint": fp, "key": key})
        return external_ids, fingerprints, content_hash_by_key, active_rows

    async def find_resumable_crawl_run(self, company_name: str) -> dict | None:
        assert self._conn is not None
        cursor = await self._conn.execute(
            """
            SELECT * FROM crawl_runs
            WHERE company_name = ?
              AND status IN ('running', 'interrupted', 'queued')
            ORDER BY id DESC
            LIMIT 1
            """,
            (company_name,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    # --- Phase 5 ops aggregates (admin / health / metrics) ---

    async def list_crawl_runs(
        self,
        *,
        statuses: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict]:
        assert self._conn is not None
        limit = max(1, min(int(limit), 500))
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            cursor = await self._conn.execute(
                f"""
                SELECT * FROM crawl_runs
                WHERE status IN ({placeholders})
                ORDER BY id DESC
                LIMIT ?
                """,
                (*statuses, limit),
            )
        else:
            cursor = await self._conn.execute(
                "SELECT * FROM crawl_runs ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        return [dict(row) for row in await cursor.fetchall()]

    async def count_crawl_runs_by_status(self) -> dict[str, int]:
        assert self._conn is not None
        cursor = await self._conn.execute(
            "SELECT status, COUNT(*) AS c FROM crawl_runs GROUP BY status"
        )
        return {str(row["status"]): int(row["c"]) for row in await cursor.fetchall()}

    async def count_reviews_collected_since(self, iso_ts: str) -> int:
        assert self._conn is not None
        cursor = await self._conn.execute(
            "SELECT COUNT(*) AS c FROM reviews WHERE collected_at >= ?",
            (iso_ts,),
        )
        row = await cursor.fetchone()
        return int(row["c"] if row else 0)

    async def count_reviews_pending_analysis(self) -> int:
        assert self._conn is not None
        cursor = await self._conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM reviews r
            LEFT JOIN review_analyses a ON a.review_id = r.id
            WHERE a.review_id IS NULL
            """
        )
        row = await cursor.fetchone()
        return int(row["c"] if row else 0)

    async def count_analysis_jobs_by_status(self) -> dict[str, int]:
        assert self._conn is not None
        cursor = await self._conn.execute(
            "SELECT status, COUNT(*) AS c FROM analysis_jobs GROUP BY status"
        )
        return {str(row["status"]): int(row["c"]) for row in await cursor.fetchall()}

    async def get_last_successful_crawl(self) -> dict | None:
        assert self._conn is not None
        cursor = await self._conn.execute(
            """
            SELECT * FROM crawl_runs
            WHERE status = 'succeeded'
            ORDER BY COALESCE(finished_at, created_at) DESC, id DESC
            LIMIT 1
            """
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_failed_jobs_summary(self) -> dict[str, int]:
        assert self._conn is not None
        crawl_failed = await self._conn.execute(
            "SELECT COUNT(*) AS c FROM crawl_runs WHERE status IN ('failed', 'interrupted')"
        )
        crawl_row = await crawl_failed.fetchone()
        branch_failed = await self._conn.execute(
            "SELECT COUNT(*) AS c FROM crawl_branch_tasks WHERE status = 'failed'"
        )
        branch_row = await branch_failed.fetchone()
        ai_failed = await self._conn.execute(
            "SELECT COUNT(*) AS c FROM analysis_jobs WHERE status = 'failed'"
        )
        ai_row = await ai_failed.fetchone()
        return {
            "failed_crawl_runs": int(crawl_row["c"] if crawl_row else 0),
            "failed_branch_tasks": int(branch_row["c"] if branch_row else 0),
            "failed_analysis_jobs": int(ai_row["c"] if ai_row else 0),
        }

    async def get_crawl_duration_stats(self) -> dict[str, float | None]:
        assert self._conn is not None
        cursor = await self._conn.execute(
            """
            SELECT started_at, finished_at
            FROM crawl_runs
            WHERE started_at IS NOT NULL AND finished_at IS NOT NULL
            ORDER BY id DESC
            LIMIT 100
            """
        )
        durations: list[float] = []
        for row in await cursor.fetchall():
            try:
                start = datetime.fromisoformat(row["started_at"])
                end = datetime.fromisoformat(row["finished_at"])
                durations.append(max(0.0, (end - start).total_seconds()))
            except ValueError:
                continue
        if not durations:
            return {"avg_duration_seconds": None, "last_duration_seconds": None, "samples": 0}
        return {
            "avg_duration_seconds": round(sum(durations) / len(durations), 3),
            "last_duration_seconds": round(durations[0], 3),
            "samples": float(len(durations)),
        }

    async def get_avg_reviews_per_branch(self) -> float:
        assert self._conn is not None
        cursor = await self._conn.execute(
            """
            SELECT
              CASE WHEN COUNT(DISTINCT branch_id) = 0 THEN 0.0
                   ELSE CAST(COUNT(*) AS REAL) / COUNT(DISTINCT branch_id)
              END AS avg_rpb
            FROM reviews
            """
        )
        row = await cursor.fetchone()
        return float(row["avg_rpb"] if row else 0.0)

    async def count_branches_processed_in_runs(self, *, limit_runs: int = 20) -> int:
        assert self._conn is not None
        cursor = await self._conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM crawl_branch_tasks t
            WHERE t.run_id IN (
                SELECT id FROM crawl_runs ORDER BY id DESC LIMIT ?
            )
              AND t.status IN ('succeeded', 'failed', 'deleted')
            """,
            (max(1, limit_runs),),
        )
        row = await cursor.fetchone()
        return int(row["c"] if row else 0)

    async def database_size_bytes(self) -> int:
        path = Path(self.path)
        if not path.exists():
            return 0
        return int(path.stat().st_size)

    async def reset_failed_branch_tasks(self, run_id: int) -> int:
        """Re-queue failed tasks that still have attempts remaining (or bump budget)."""
        assert self._conn is not None
        cursor = await self._conn.execute(
            """
            UPDATE crawl_branch_tasks
            SET status = 'pending',
                last_error = NULL,
                max_attempts = CASE
                    WHEN attempts >= max_attempts THEN attempts + 2
                    ELSE max_attempts
                END
            WHERE run_id = ? AND status = 'failed'
            """,
            (run_id,),
        )
        await self._conn.commit()
        return int(cursor.rowcount or 0)

    async def upsert_reviews_batch(self, branch_id: int, reviews: list[Review]) -> int:
        """Batch upsert for stress / high-volume ingest (single commit)."""
        if not reviews:
            return 0
        assert self._conn is not None
        from collectors.dedupe import review_content_hash

        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for review in reviews:
            external_id = (
                review.external_id
                or f"{review.author}|{review.published_at}|{review.text[:80]}"
            )
            content_hash = review.content_hash or review_content_hash(review)
            rows.append(
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
                    review.owner_response or "",
                    review.owner_response_at or "",
                    content_hash,
                    now,
                )
            )
        await self._conn.executemany(
            """
            INSERT INTO reviews (
                branch_id, author, rating, text, published_at, language,
                source, external_id, raw_json, collected_at,
                owner_response, owner_response_at, is_deleted, content_hash, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            ON CONFLICT(branch_id, external_id) DO UPDATE SET
                author = excluded.author,
                rating = excluded.rating,
                text = excluded.text,
                published_at = excluded.published_at,
                language = excluded.language,
                raw_json = excluded.raw_json,
                collected_at = excluded.collected_at,
                owner_response = excluded.owner_response,
                owner_response_at = excluded.owner_response_at,
                is_deleted = 0,
                content_hash = excluded.content_hash,
                last_seen_at = excluded.last_seen_at
            """,
            rows,
        )
        await self._conn.commit()
        return len(rows)

    async def mark_reviews_deleted(self, branch_id: int, review_ids: list[int]) -> int:
        if not review_ids:
            return 0
        assert self._conn is not None
        placeholders = ",".join("?" for _ in review_ids)
        cursor = await self._conn.execute(
            f"""
            UPDATE reviews
            SET is_deleted = 1
            WHERE branch_id = ? AND id IN ({placeholders})
            """,
            (branch_id, *review_ids),
        )
        await self._conn.commit()
        return int(cursor.rowcount or 0)

    async def mark_branch_success(self, branch_id: int) -> None:
        assert self._conn is not None
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            """
            UPDATE branches
            SET is_deleted = 0, last_seen_at = ?, last_success_at = ?
            WHERE id = ?
            """,
            (now, now, branch_id),
        )
        await self._conn.commit()

    async def _ensure_ops_metric_samples(self) -> None:
        """Durable metric samples so restarts do not wipe ops history."""
        assert self._conn is not None
        await self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ops_metric_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                value REAL NOT NULL,
                labels_json TEXT NOT NULL DEFAULT '{}',
                recorded_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ops_metric_samples_name_time
                ON ops_metric_samples(name, recorded_at);
            """
        )
        await self._conn.commit()

    async def insert_metric_samples(self, samples: list[dict]) -> int:
        assert self._conn is not None
        if not samples:
            return 0
        rows = []
        for sample in samples:
            labels = sample.get("labels") or {}
            labels_json = labels if isinstance(labels, str) else json.dumps(labels, ensure_ascii=False)
            rows.append(
                (
                    str(sample.get("name") or ""),
                    float(sample.get("value") or 0.0),
                    labels_json,
                    str(sample.get("recorded_at") or datetime.now(timezone.utc).isoformat()),
                )
            )
        await self._conn.executemany(
            """
            INSERT INTO ops_metric_samples (name, value, labels_json, recorded_at)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )
        await self._conn.commit()
        return len(rows)

    async def list_recent_metric_samples(self, *, limit: int = 200) -> list[dict]:
        assert self._conn is not None
        cursor = await self._conn.execute(
            """
            SELECT id, name, value, labels_json, recorded_at
            FROM ops_metric_samples
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        out = []
        for row in await cursor.fetchall():
            item = dict(row)
            try:
                item["labels"] = json.loads(item.pop("labels_json") or "{}")
            except json.JSONDecodeError:
                item["labels"] = {}
            out.append(item)
        return out

    async def get_ops_dashboard(self) -> dict:
        """Aggregate payload for admin monitoring dashboard."""
        today_start = (
            datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        ).isoformat()
        status_counts = await self.count_crawl_runs_by_status()
        ai_jobs = await self.count_analysis_jobs_by_status()
        duration = await self.get_crawl_duration_stats()
        failed = await self.get_failed_jobs_summary()
        last_ok = await self.get_last_successful_crawl()
        pending_ai = await self.count_reviews_pending_analysis()
        queue_len = int(ai_jobs.get("queued", 0) + ai_jobs.get("running", 0))
        return {
            "running_crawls": await self.list_crawl_runs(statuses=["running"], limit=20),
            "completed_crawls": await self.list_crawl_runs(statuses=["succeeded"], limit=20),
            "failed_crawls": await self.list_crawl_runs(
                statuses=["failed", "interrupted"], limit=20
            ),
            "crawl_status_counts": status_counts,
            "reviews_collected_today": await self.count_reviews_collected_since(today_start),
            "reviews_pending_ai_analysis": pending_ai,
            "ai_queue_length": queue_len,
            "analysis_jobs_by_status": ai_jobs,
            "branches_processed_recent": await self.count_branches_processed_in_runs(),
            "crawl_duration": duration,
            "average_reviews_per_branch": round(await self.get_avg_reviews_per_branch(), 3),
            "failed_jobs": failed,
            "last_successful_crawl": last_ok,
        }

    async def get_system_health(self) -> dict:
        dash = await self.get_ops_dashboard()
        ai_jobs = dash["analysis_jobs_by_status"]
        failed = dash["failed_jobs"]
        queue_len = dash["ai_queue_length"]
        db_bytes = await self.database_size_bytes()
        status = "ok"
        if failed["failed_crawl_runs"] or failed["failed_analysis_jobs"]:
            status = "attention"
        if dash["crawl_status_counts"].get("running", 0) > 3:
            status = "busy"
        return {
            "status": status,
            "database_size_bytes": db_bytes,
            "database_size_mb": round(db_bytes / (1024 * 1024), 3),
            "queue_health": {
                "ai_queue_length": queue_len,
                "queued": int(ai_jobs.get("queued", 0)),
                "running": int(ai_jobs.get("running", 0)),
                "failed": int(ai_jobs.get("failed", 0)),
                "succeeded": int(ai_jobs.get("succeeded", 0)),
            },
            "failed_jobs": failed,
            "last_successful_crawl": dash["last_successful_crawl"],
            "ai_processing_status": {
                "pending_reviews": dash["reviews_pending_ai_analysis"],
                "queue_length": queue_len,
                "by_status": ai_jobs,
            },
            "reviews_collected_today": dash["reviews_collected_today"],
            "average_reviews_per_branch": dash["average_reviews_per_branch"],
        }
