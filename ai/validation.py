from __future__ import annotations

from pydantic import ValidationError

from ai.taxonomy import CATEGORY_TAXONOMY, SCHEMA_VERSION
from models.analysis import AnalysisDTO


class AnalysisValidationError(ValueError):
    pass


def validate_taxonomy_values(categories: list[str]) -> None:
    unknown = sorted({value for value in categories if value not in CATEGORY_TAXONOMY})
    if unknown:
        raise AnalysisValidationError(f"Unknown categories outside taxonomy: {unknown}")


def validate_analysis_payload(payload: dict | AnalysisDTO) -> AnalysisDTO:
    """Validate schema + taxonomy. Raises AnalysisValidationError on failure."""
    try:
        if isinstance(payload, AnalysisDTO):
            dto = AnalysisDTO.model_validate(payload.model_dump())
        else:
            dto = AnalysisDTO.model_validate(payload)
    except ValidationError as exc:
        raise AnalysisValidationError(str(exc)) from exc

    validate_taxonomy_values(dto.complaint_categories)
    validate_taxonomy_values(dto.positive_categories)

    if dto.schema_version != SCHEMA_VERSION:
        raise AnalysisValidationError(
            f"Unsupported schema_version={dto.schema_version}; expected {SCHEMA_VERSION}"
        )
    return dto
