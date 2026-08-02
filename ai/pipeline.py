from __future__ import annotations

import hashlib

from ai.adapters.base import ModelAdapter
from ai.taxonomy import PROMPT_VERSION, SCHEMA_VERSION
from ai.validation import AnalysisValidationError, validate_analysis_payload
from core.db import Database
from models.analysis import AnalysisDTO
from models.review import Review


def compute_input_hash(
    text: str,
    *,
    schema_version: str = SCHEMA_VERSION,
    prompt_version: str = PROMPT_VERSION,
    model_id: str,
) -> str:
    payload = f"{text.strip()}|{schema_version}|{prompt_version}|{model_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AnalysisPipeline:
    """Review -> adapter -> validate -> persist."""

    def __init__(self, db: Database, adapter: ModelAdapter):
        self.db = db
        self.adapter = adapter

    async def process_review(self, review_id: int, review: Review) -> AnalysisDTO:
        existing_hash = await self.db.get_analysis_input_hash(review_id)
        input_hash = compute_input_hash(
            review.text or "",
            model_id=self.adapter.id,
        )
        if existing_hash and existing_hash == input_hash:
            cached = await self.db.get_analysis_dto(review_id)
            if cached is not None:
                return cached

        raw = await self.adapter.extract(review, meta={"review_id": review_id})
        try:
            dto = validate_analysis_payload(raw)
        except AnalysisValidationError as exc:
            failed = AnalysisDTO(
                sentiment="Neutral",
                status="failed",
                error=str(exc),
                provider=getattr(raw, "provider", "unknown"),
                model_id=self.adapter.id,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                confidence_overall=0.0,
                raw_response={"validation_error": str(exc)},
            )
            await self.db.upsert_review_analysis(
                review_id,
                failed,
                input_hash=input_hash,
            )
            raise

        await self.db.upsert_review_analysis(
            review_id,
            dto,
            input_hash=input_hash,
        )
        return dto
