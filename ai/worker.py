from __future__ import annotations

from ai.adapters.base import ModelAdapter
from ai.pipeline import AnalysisPipeline
from ai.validation import AnalysisValidationError
from core.db import Database
from models.review import Review


class AnalysisWorker:
    """Process queued analysis_jobs using the configured adapter."""

    def __init__(self, db: Database, adapter: ModelAdapter):
        self.db = db
        self.pipeline = AnalysisPipeline(db, adapter)

    async def enqueue_review(self, review_id: int) -> int:
        return await self.db.create_analysis_job(
            scope="review",
            scope_id=review_id,
            total_items=1,
        )

    async def process_next_job(self) -> dict | None:
        job = await self.db.claim_next_analysis_job()
        if job is None:
            return None

        job_id = int(job["id"])
        scope = job["scope"]
        scope_id = job["scope_id"]
        done = 0
        failed = 0
        error: str | None = None

        try:
            if scope != "review" or scope_id is None:
                raise ValueError(f"Unsupported job scope for foundation worker: {scope}")

            row = await self.db.get_review_row(int(scope_id))
            if row is None:
                raise ValueError(f"Review not found: {scope_id}")

            review = Review(
                author=row["author"] or "",
                rating=float(row["rating"] or 0),
                text=row["text"] or "",
                published_at=row["published_at"] or "",
                language=row["language"] or "",
                external_id=row["external_id"] or "",
                branch_name=row["branch_name"] or "",
                source=row["source"] or "google_maps",
            )
            await self.pipeline.process_review(int(scope_id), review)
            done = 1
            await self.db.finish_analysis_job(
                job_id,
                status="succeeded",
                done_items=done,
                failed_items=failed,
            )
        except AnalysisValidationError as exc:
            failed = 1
            error = str(exc)
            await self.db.finish_analysis_job(
                job_id,
                status="failed",
                done_items=done,
                failed_items=failed,
                error=error,
            )
        except Exception as exc:  # noqa: BLE001 - worker boundary
            failed = 1
            error = str(exc)
            await self.db.finish_analysis_job(
                job_id,
                status="failed",
                done_items=done,
                failed_items=failed,
                error=error,
            )

        return {
            "job_id": job_id,
            "scope": scope,
            "scope_id": scope_id,
            "done_items": done,
            "failed_items": failed,
            "error": error,
        }

    async def run_until_idle(self, *, max_jobs: int = 100) -> list[dict]:
        results: list[dict] = []
        for _ in range(max_jobs):
            result = await self.process_next_job()
            if result is None:
                break
            results.append(result)
        return results
