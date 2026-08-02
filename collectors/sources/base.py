from __future__ import annotations

from typing import Protocol

from models.branch import Branch
from models.review import Review


class BranchReviewSource(Protocol):
    """Provider-agnostic branch/review collection interface."""

    async def discover_branches(self, company_name: str) -> list[Branch]:
        ...

    async def collect_reviews(self, branch: Branch) -> list[Review]:
        ...

    async def close(self) -> None:
        ...


class SourceInfo:
    def __init__(self, source_id: str, *, supports_incremental: bool = True):
        self.source_id = source_id
        self.supports_incremental = supports_incremental
