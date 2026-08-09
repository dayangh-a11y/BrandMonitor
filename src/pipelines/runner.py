"""Run one or all feature pipelines against the warehouse."""

from __future__ import annotations

from loguru import logger
from sqlalchemy.orm import Session

from src.database.features import FeaturePipelineRun
from src.pipelines.registry import get_pipeline, list_pipelines


def build_features(
    session: Session,
    *,
    pipeline_names: list[str] | None = None,
) -> list[FeaturePipelineRun]:
    names = pipeline_names or list_pipelines()
    runs: list[FeaturePipelineRun] = []
    for name in names:
        pipeline = get_pipeline(name)
        logger.info("Building features via pipeline={}", name)
        runs.append(pipeline.run(session))
    return runs
