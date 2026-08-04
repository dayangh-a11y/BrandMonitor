"""HTTP API for the dedicated Iran Post module (national operator)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api.auth import require_api_token
from postal.iran_post.provider import IranPostModule

router = APIRouter(
    prefix="/postal/iran-post",
    tags=["iran-post"],
    dependencies=[Depends(require_api_token)],
)


class CompareIn(BaseModel):
    mode: str = Field(
        "national",
        description="national | fair (national_ranking | fair_comparison also accepted)",
    )
    slugs: list[str] | None = Field(
        default=None,
        description="Company slugs to include. Fair mode requires >= 2.",
    )


def _module() -> IranPostModule:
    return IranPostModule()


@router.get("/catalog")
def iran_post_catalog() -> dict[str, Any]:
    return _module().catalog()


@router.get("/profile")
def iran_post_profile() -> dict[str, Any]:
    return _module().official_profile()


@router.get("/snapshot")
def iran_post_snapshot() -> dict[str, Any]:
    return _module().snapshot()


@router.get("/maps-reviews")
def iran_post_maps_reviews(
    limit: int = Query(200, ge=1, le=1000),
) -> dict[str, Any]:
    return _module().maps_reviews(limit=limit)


@router.get("/branches")
def iran_post_branches() -> dict[str, Any]:
    offices = _module().branch_directory()
    return {
        "role": "national_postal_operator",
        "source_policy": "warehouse_google_maps_only",
        "count": len(offices),
        "branches": offices,
    }


@router.get("/compare/national")
def iran_post_national(
    slugs: list[str] | None = Query(default=None),
) -> dict[str, Any]:
    return _module().national_ranking(slugs=slugs).as_dict()


@router.get("/compare/fair")
def iran_post_fair(
    slugs: list[str] = Query(
        default=["post", "tipax", "chapar"],
        description="Companies to intersect; must share observed cities.",
    ),
) -> dict[str, Any]:
    return _module().fair_comparison(slugs=slugs).as_dict()


@router.post("/compare")
def iran_post_compare(body: CompareIn) -> dict[str, Any]:
    return _module().compare(mode=body.mode, slugs=body.slugs)
