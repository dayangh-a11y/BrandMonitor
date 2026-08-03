from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


CrawlMode = Literal["full", "incremental"]
CrawlRunStatus = Literal["queued", "running", "succeeded", "failed", "interrupted"]
BranchTaskStatus = Literal["pending", "running", "succeeded", "failed", "skipped", "deleted"]


@dataclass
class CrawlConfig:
    company_name: str
    mode: CrawlMode = "full"
    max_branches: int | None = None
    max_reviews_per_branch: int | None = None
    max_attempts: int = 3
    headless: bool = True
    branch_place_id: str | None = None
    branch_name: str | None = None
    detect_deleted_reviews: bool = True
    detect_deleted_branches: bool = True


@dataclass
class CrawlProgress:
    run_id: int
    status: CrawlRunStatus
    total_branches: int = 0
    pending: int = 0
    running: int = 0
    succeeded: int = 0
    failed: int = 0
    deleted: int = 0
    reviews_new: int = 0
    reviews_updated: int = 0


@dataclass
class CrawlReport:
    run_id: int
    company_name: str
    mode: CrawlMode
    status: CrawlRunStatus
    started_at: str | None
    finished_at: str | None
    duration_seconds: float | None
    branches_discovered: int
    branches_succeeded: int
    branches_failed: int
    branches_deleted: int
    reviews_found: int
    reviews_new: int
    reviews_updated: int
    reviews_deleted: int = 0
    retries: int = 0
    errors: list[str] = field(default_factory=list)
    stats: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "company_name": self.company_name,
            "mode": self.mode,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "branches_discovered": self.branches_discovered,
            "branches_succeeded": self.branches_succeeded,
            "branches_failed": self.branches_failed,
            "branches_deleted": self.branches_deleted,
            "reviews_found": self.reviews_found,
            "reviews_new": self.reviews_new,
            "reviews_updated": self.reviews_updated,
            "reviews_deleted": self.reviews_deleted,
            "retries": self.retries,
            "errors": self.errors,
            "stats": self.stats,
        }
