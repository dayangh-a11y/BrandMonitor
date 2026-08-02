from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from api.auth import require_api_token
from api.deps import get_db
from api.errors import APIError
from api.schemas import (
    BranchOut,
    CompanyOut,
    PaginatedReviews,
    ReviewOut,
    ScoreOut,
    SearchResponse,
)
from core.db import Database

router = APIRouter(dependencies=[Depends(require_api_token)])

SortParam = Literal["newest", "oldest", "highest_score", "lowest_score"]


def _company_out(row: dict) -> CompanyOut:
    return CompanyOut(
        id=row["id"],
        name=row["name"],
        source=row["source"],
        created_at=row["created_at"],
        branch_count=int(row.get("branch_count") or 0),
        review_count=int(row.get("review_count") or 0),
        latest_score=row.get("latest_score"),
    )


def _branch_out(row: dict) -> BranchOut:
    return BranchOut(
        id=row["id"],
        company_id=row["company_id"],
        name=row["name"],
        address=row.get("address") or "",
        rating=float(row.get("rating") or 0),
        review_count=int(row.get("review_count") or 0),
        maps_url=row.get("maps_url") or "",
        place_id=row.get("place_id") or "",
        collected_at=row["collected_at"],
        latest_score=row.get("latest_score"),
        company_name=row.get("company_name"),
    )


@router.get("/companies", response_model=list[CompanyOut])
async def list_companies(
    sort: SortParam = Query("newest"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_db),
) -> list[CompanyOut]:
    rows = await db.list_companies(sort=sort, limit=limit, offset=offset)
    return [_company_out(row) for row in rows]


@router.get("/companies/{company_id}", response_model=CompanyOut)
async def get_company(company_id: int, db: Database = Depends(get_db)) -> CompanyOut:
    row = await db.get_company(company_id)
    if row is None:
        raise APIError(404, "company_not_found", f"Company {company_id} not found")
    return _company_out(row)


@router.get("/companies/{company_id}/branches", response_model=list[BranchOut])
async def list_company_branches(
    company_id: int,
    sort: SortParam = Query("newest"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_db),
) -> list[BranchOut]:
    company = await db.get_company(company_id)
    if company is None:
        raise APIError(404, "company_not_found", f"Company {company_id} not found")
    rows = await db.list_company_branches(
        company_id,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return [_branch_out(row) for row in rows]


@router.get("/companies/{company_id}/score", response_model=ScoreOut)
async def get_company_score(company_id: int, db: Database = Depends(get_db)) -> ScoreOut:
    company = await db.get_company(company_id)
    if company is None:
        raise APIError(404, "company_not_found", f"Company {company_id} not found")
    score = await db.get_company_score(company_id)
    if score is None:
        raise APIError(404, "score_not_found", f"No score for company {company_id}")
    return ScoreOut(
        entity_type="company",
        entity_id=company_id,
        score=float(score["score"]),
        components=score.get("components") or {},
        algorithm_version=score.get("algorithm_version") or "score_v1",
        calculated_at=score["calculated_at"],
    )


@router.get("/branches/{branch_id}", response_model=BranchOut)
async def get_branch(branch_id: int, db: Database = Depends(get_db)) -> BranchOut:
    row = await db.get_branch(branch_id)
    if row is None:
        raise APIError(404, "branch_not_found", f"Branch {branch_id} not found")
    return _branch_out(row)


@router.get("/branches/{branch_id}/reviews", response_model=PaginatedReviews)
async def list_branch_reviews(
    branch_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sentiment: str | None = Query(
        None,
        description="Filter by analysis sentiment (Positive/Neutral/Negative)",
    ),
    category: str | None = Query(None, description="Filter by taxonomy category"),
    city: str | None = Query(None, description="Filter by mentioned city"),
    sort: SortParam = Query("newest"),
    db: Database = Depends(get_db),
) -> PaginatedReviews:
    branch = await db.get_branch(branch_id)
    if branch is None:
        raise APIError(404, "branch_not_found", f"Branch {branch_id} not found")

    if sentiment and sentiment.lower() not in {"positive", "neutral", "negative"}:
        raise APIError(
            422,
            "invalid_sentiment",
            "sentiment must be Positive, Neutral, or Negative",
        )

    rows, total = await db.list_branch_reviews(
        branch_id,
        limit=limit,
        offset=offset,
        sentiment=sentiment,
        category=category,
        city=city,
        sort=sort,
    )
    items = [ReviewOut.model_validate(row) for row in rows]
    return PaginatedReviews(items=items, total=total, limit=limit, offset=offset)


@router.get("/branches/{branch_id}/score", response_model=ScoreOut)
async def get_branch_score(branch_id: int, db: Database = Depends(get_db)) -> ScoreOut:
    branch = await db.get_branch(branch_id)
    if branch is None:
        raise APIError(404, "branch_not_found", f"Branch {branch_id} not found")
    score = await db.get_branch_score(branch_id)
    if score is None:
        raise APIError(404, "score_not_found", f"No score for branch {branch_id}")
    return ScoreOut(
        entity_type="branch",
        entity_id=branch_id,
        score=float(score["score"]),
        components=score.get("components") or {},
        algorithm_version=score.get("algorithm_version") or "score_v1",
        calculated_at=score["calculated_at"],
    )


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(20, ge=1, le=100),
    sort: SortParam = Query("newest"),
    db: Database = Depends(get_db),
) -> SearchResponse:
    result = await db.search(q, limit=limit, sort=sort)
    return SearchResponse(
        query=q,
        companies=[_company_out(row) for row in result["companies"]],
        branches=[_branch_out(row) for row in result["branches"]],
    )
