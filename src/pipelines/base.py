"""Feature pipeline interface — all features must be produced through this."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from src.database.features import FeaturePipelineRun


class FeaturePipeline(ABC):
    """
    Base class for rebuildable feature jobs.

    Implementations must:
    - read only from Raw tables
    - write only to Feature tables
    - be idempotent (safe to re-run)
    """

    name: str
    version: str = "1"

    @abstractmethod
    def compute(self, session: Session, *, pipeline_run_id: int) -> int:
        """Compute/upsert features. Return number of rows written/updated."""

    def run(self, session: Session, *, params: dict[str, Any] | None = None) -> FeaturePipelineRun:
        run = FeaturePipelineRun(
            pipeline_name=self.name,
            pipeline_version=self.version,
            status="running",
            params_json=params or {},
        )
        session.add(run)
        session.flush()
        logger.info("Feature pipeline start name={} version={} run_id={}", self.name, self.version, run.id)
        try:
            count = self.compute(session, pipeline_run_id=run.id)
            run.rows_upserted = count
            run.status = "success"
            run.finished_at = datetime.now(timezone.utc)
            session.flush()
            logger.info(
                "Feature pipeline success name={} rows={}",
                self.name,
                count,
            )
            return run
        except Exception as exc:  # noqa: BLE001
            run.status = "failed"
            run.error_message = str(exc)[:1000]
            run.finished_at = datetime.now(timezone.utc)
            session.flush()
            logger.exception("Feature pipeline failed name={}: {}", self.name, exc)
            raise
