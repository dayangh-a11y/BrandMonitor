"""Optional HTTP routes for Five-Parreh Phase 1 (no prediction/ranking)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.five_parreh import FiveParrehValidationError, generate_combinations

# Guard against huge JSON payloads. Summary/cost always available without listing.
DEFAULT_MAX_COMBINATIONS_IN_RESPONSE = 1000
HARD_MAX_COMBINATIONS = 100_000

router = APIRouter(prefix="/five-parreh", tags=["five-parreh"])


class FiveParrehRaceIn(BaseModel):
    race_id: str
    horses: list[Any] = Field(..., min_length=1)


class FiveParrehCombinationsRequest(BaseModel):
    races: list[FiveParrehRaceIn] = Field(..., min_length=5, max_length=5)
    price_per_combination: int | float | None = None
    include_combinations: bool = True
    max_combinations_in_response: int = Field(
        default=DEFAULT_MAX_COMBINATIONS_IN_RESPONSE,
        ge=0,
        le=HARD_MAX_COMBINATIONS,
    )


@router.post("/combinations")
def post_combinations(body: FiveParrehCombinationsRequest) -> dict[str, Any]:
    """Build Five-Parreh combinations from selections (Cartesian product only)."""
    payload = {
        "races": [{"race_id": r.race_id, "horses": r.horses} for r in body.races]
    }
    try:
        # Always compute summary first without materializing if oversized.
        summary_only = generate_combinations(
            payload,
            price_per_combination=body.price_per_combination,
            include_combinations=False,
        )
    except FiveParrehValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    total = summary_only.summary.total_combinations
    if total > HARD_MAX_COMBINATIONS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"total_combinations={total} exceeds hard limit "
                f"{HARD_MAX_COMBINATIONS}. Reduce selections per race."
            ),
        )

    include = body.include_combinations
    if include and total > body.max_combinations_in_response:
        # Protect response size: return summary only with a clear flag.
        out = summary_only.to_dict(include_combinations=False)
        out["combinations_omitted"] = True
        out["combinations_omission_reason"] = (
            f"total_combinations={total} exceeds max_combinations_in_response="
            f"{body.max_combinations_in_response}. "
            "Set include_combinations=false for summary-only, or raise the cap "
            f"(max {HARD_MAX_COMBINATIONS}) if you truly need the full list."
        )
        return out

    result = generate_combinations(
        payload,
        price_per_combination=body.price_per_combination,
        include_combinations=include,
    )
    return result.to_dict(include_combinations=include)
