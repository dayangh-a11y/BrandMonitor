from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


SortLiteral = Literal["newest", "oldest", "highest_score", "lowest_score"]


class CompanyOut(BaseModel):
    id: int
    name: str
    source: str
    created_at: str
    branch_count: int = 0
    review_count: int = 0
    latest_score: float | None = None


class BranchOut(BaseModel):
    id: int
    company_id: int
    name: str
    address: str
    rating: float
    review_count: int
    maps_url: str = ""
    place_id: str = ""
    collected_at: str
    latest_score: float | None = None
    company_name: str | None = None


class ReviewOut(BaseModel):
    id: int
    branch_id: int
    author: str
    rating: float
    text: str
    published_at: str
    language: str = ""
    source: str
    external_id: str = ""
    collected_at: str
    sentiment: str | None = None
    complaint_categories: list[str] = Field(default_factory=list)
    positive_categories: list[str] = Field(default_factory=list)
    mentioned_city: str | None = None


class ScoreOut(BaseModel):
    entity_type: Literal["company", "branch"]
    entity_id: int
    score: float
    components: dict[str, Any] = Field(default_factory=dict)
    algorithm_version: str
    calculated_at: str


class PaginatedReviews(BaseModel):
    items: list[ReviewOut]
    total: int
    limit: int
    offset: int


class SearchResponse(BaseModel):
    query: str
    companies: list[CompanyOut]
    branches: list[BranchOut]


class HealthOut(BaseModel):
    status: str
    stats: dict[str, int]
