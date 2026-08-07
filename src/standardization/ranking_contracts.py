"""Module 6 — Ranking Engine contracts.

Every ranking must define:
  Eligibility, Ranking Formula, Tie Break, Minimum Starts,
  Minimum Confidence, Version.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.standardization.constants import DEFAULT_MIN_STARTS


@dataclass(frozen=True, slots=True)
class RankingContract:
    board: str
    title: str
    eligibility: str
    ranking_formula: str
    tie_break: tuple[str, ...]
    minimum_starts: int
    minimum_confidence: str
    version: str
    score_field: str
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "board": self.board,
            "title": self.title,
            "eligibility": self.eligibility,
            "ranking_formula": self.ranking_formula,
            "tie_break": list(self.tie_break),
            "minimum_starts": self.minimum_starts,
            "minimum_confidence": self.minimum_confidence,
            "version": self.version,
            "score_field": self.score_field,
            "notes": self.notes,
        }


RANKING_CONTRACTS: dict[str, RankingContract] = {
    "best_season": RankingContract(
        board="best_season",
        title="Season Best Horse",
        eligibility=(
            "starts >= minimum_starts; season scope; "
            "gate fails if max(starts)<=1 or zero qualified"
        ),
        ranking_formula="ORDER BY performance_rating DESC",
        tie_break=("wins", "places", "avg_finish ASC", "form_score_5", "earnings_total"),
        minimum_starts=DEFAULT_MIN_STARTS,
        minimum_confidence="high",  # sample band 'valid' mapped → high
        version="2.0.0",
        score_field="performance_rating",
        notes="Earnings never dominate PR; earnings only last tie-break.",
    ),
    "most_successful": RankingContract(
        board="most_successful",
        title="Most Successful Horse",
        eligibility="starts >= minimum_starts",
        ranking_formula="ORDER BY wins DESC",
        tie_break=("places", "performance_rating", "earnings_total"),
        minimum_starts=DEFAULT_MIN_STARTS,
        minimum_confidence="high",
        version="2.0.0",
        score_field="wins",
    ),
    "highest_earnings": RankingContract(
        board="highest_earnings",
        title="Highest Earnings Horse",
        eligibility="starts >= 1 (earnings board)",
        ranking_formula="ORDER BY earnings_total DESC",
        tie_break=("wins", "performance_rating"),
        minimum_starts=1,
        minimum_confidence="very_low",
        version="2.0.0",
        score_field="earnings_total",
        notes="Separate concept — not Season Best.",
    ),
    "highest_win_rate": RankingContract(
        board="highest_win_rate",
        title="Highest Win Rate Horse",
        eligibility="starts >= minimum_starts",
        ranking_formula="ORDER BY win_rate DESC",
        tie_break=("wins", "starts", "performance_rating"),
        minimum_starts=DEFAULT_MIN_STARTS,
        minimum_confidence="high",
        version="2.0.0",
        score_field="win_rate",
    ),
    "best_form": RankingContract(
        board="best_form",
        title="Best Form Horse",
        eligibility="starts >= 3",
        ranking_formula="ORDER BY form_score_5 DESC",
        tie_break=("form_score_3", "performance_rating"),
        minimum_starts=3,
        minimum_confidence="medium",
        version="2.0.0",
        score_field="form_score_5",
    ),
    "most_consistent": RankingContract(
        board="most_consistent",
        title="Most Consistent Horse",
        eligibility="starts >= minimum_starts",
        ranking_formula="ORDER BY consistency_score DESC",
        tie_break=("starts", "performance_rating"),
        minimum_starts=DEFAULT_MIN_STARTS,
        minimum_confidence="high",
        version="2.0.0",
        score_field="consistency_score",
    ),
}


def get_contract(board: str) -> RankingContract | None:
    return RANKING_CONTRACTS.get(board)


def list_contracts() -> list[dict[str, Any]]:
    return [c.to_dict() for c in RANKING_CONTRACTS.values()]
