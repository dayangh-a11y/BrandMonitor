from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from core.logging_setup import get_logger

log = get_logger("scoring")

ALGORITHM_VERSION = "score_v1"
PRIOR_SCORE = 55.0
KAPPA_PRIOR = 5.0  # stronger shrinkage with few reviews

_SENTIMENT = {"Positive": 100.0, "Neutral": 50.0, "Negative": 0.0}
_QUALITY = {"good": 100.0, "average": 50.0, "bad": 0.0}
_SPEED = {"fast": 100.0, "normal": 55.0, "slow": 0.0}
_PRICING = {"cheap": 90.0, "fair": 70.0, "expensive": 20.0}
_URGENCY = {"low": 0.0, "medium": -2.0, "high": -5.0}
_DIMENSION_KEYS = (
    "delivery_speed",
    "customer_service",
    "staff_behavior",
    "pricing",
    "tracking",
    "professionalism",
)


@dataclass
class BranchScoreResult:
    score: float
    components: dict[str, Any]


@dataclass
class CompanyScoreResult:
    score: float
    components: dict[str, Any]


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return []


def _analysis_weight(row: dict[str, Any]) -> float:
    conf = float(row.get("confidence_overall") or 0.5)
    return max(0.15, min(1.0, conf))


def _dimension_values(row: dict[str, Any]) -> list[float]:
    values: list[float] = []
    speed = row.get("delivery_speed")
    if speed in _SPEED:
        values.append(_SPEED[speed])
    for key in ("customer_service", "staff_behavior", "tracking", "professionalism"):
        raw = row.get(key)
        if raw in _QUALITY:
            values.append(_QUALITY[raw])
    pricing = row.get("pricing")
    if pricing in _PRICING:
        values.append(_PRICING[pricing])
    damage = row.get("package_damage")
    if damage is True:
        values.append(10.0)
    elif damage is False:
        values.append(90.0)
    return values


def _top_shares(counter: Counter[str], *, total: float, limit: int = 3) -> list[dict[str, Any]]:
    if total <= 0:
        return []
    return [
        {"category": cat, "share": round(count / total, 4)}
        for cat, count in counter.most_common(limit)
    ]


def compute_branch_score_v1(analyses: list[dict[str, Any]]) -> BranchScoreResult:
    """
    Deterministic branch score from review_analyses rows.

    Components intentionally match the demo/API expected shape.
    """
    usable = [
        row
        for row in analyses
        if (row.get("status") or "succeeded") == "succeeded"
    ]
    if not usable:
        return BranchScoreResult(
            score=PRIOR_SCORE,
            components={
                "algorithm_version": ALGORITHM_VERSION,
                "sentiment_score": PRIOR_SCORE,
                "dimension_score": PRIOR_SCORE,
                "complaint_penalty": 0.0,
                "positive_reward": 0.0,
                "urgency_penalty": 0.0,
                "kappa": 0.0,
                "n_eff": 0.0,
                "raw": PRIOR_SCORE,
                "top_complaints": [],
                "top_positives": [],
                "why": ["No successful analyses yet; using prior score."],
            },
        )

    weights = [_analysis_weight(row) for row in usable]
    w_sum = sum(weights) or 1.0

    sentiment_score = (
        sum(_SENTIMENT.get(str(row.get("sentiment")), 50.0) * w for row, w in zip(usable, weights))
        / w_sum
    )

    dim_num = 0.0
    dim_den = 0.0
    for row, w in zip(usable, weights):
        dims = _dimension_values(row)
        if not dims:
            continue
        dim_num += (sum(dims) / len(dims)) * w
        dim_den += w
    dimension_score = dim_num / dim_den if dim_den else sentiment_score

    complaint_counter: Counter[str] = Counter()
    positive_counter: Counter[str] = Counter()
    urgency_pen = 0.0
    for row, w in zip(usable, weights):
        for cat in _as_list(row.get("complaint_categories")):
            complaint_counter[str(cat)] += w
        for cat in _as_list(row.get("positive_categories")):
            positive_counter[str(cat)] += w
        urgency_pen += _URGENCY.get(str(row.get("urgency") or "low"), 0.0) * w
    urgency_penalty = urgency_pen / w_sum

    complaint_mass = sum(complaint_counter.values())
    positive_mass = sum(positive_counter.values())
    complaint_penalty = -min(25.0, 12.0 * (complaint_mass / w_sum))
    positive_reward = min(15.0, 8.0 * (positive_mass / w_sum))

    raw = (
        0.50 * sentiment_score
        + 0.35 * dimension_score
        + complaint_penalty
        + positive_reward
        + urgency_penalty
    )
    raw = max(0.0, min(100.0, raw))

    n_eff = float(w_sum)
    kappa = n_eff / (n_eff + KAPPA_PRIOR)
    score = kappa * raw + (1.0 - kappa) * PRIOR_SCORE
    score = round(max(0.0, min(100.0, score)), 1)

    top_complaints = _top_shares(complaint_counter, total=complaint_mass or 1.0)
    top_positives = _top_shares(positive_counter, total=positive_mass or 1.0)

    why: list[str] = []
    if top_complaints:
        why.append(
            f"Top complaints: {', '.join(c['category'] for c in top_complaints)} "
            f"(penalty {complaint_penalty:.1f})."
        )
    if top_positives:
        why.append(
            f"Positive signals: {', '.join(c['category'] for c in top_positives)} "
            f"(reward +{positive_reward:.1f})."
        )
    why.append(
        f"Evidence weight n_eff={n_eff:.1f} (kappa={kappa:.2f}); "
        f"shrunk toward prior {PRIOR_SCORE}."
    )
    if n_eff < 3:
        why.append("Low review volume — treat score as provisional.")

    components = {
        "algorithm_version": ALGORITHM_VERSION,
        "sentiment_score": round(sentiment_score, 1),
        "dimension_score": round(dimension_score, 1),
        "complaint_penalty": round(complaint_penalty, 1),
        "positive_reward": round(positive_reward, 1),
        "urgency_penalty": round(urgency_penalty, 1),
        "kappa": round(kappa, 2),
        "n_eff": round(n_eff, 2),
        "raw": round(raw, 1),
        "top_complaints": top_complaints,
        "top_positives": top_positives,
        "why": why,
    }
    log.info("branch_score_computed score=%s n_eff=%s", score, n_eff)
    return BranchScoreResult(score=score, components=components)


def compute_company_score_v1(
    branch_results: list[tuple[str, BranchScoreResult]],
) -> CompanyScoreResult:
    if not branch_results:
        return CompanyScoreResult(
            score=PRIOR_SCORE,
            components={
                "algorithm_version": ALGORITHM_VERSION,
                "branch_scores": {},
                "why": ["No branch scores available."],
            },
        )

    weighted = 0.0
    weight_sum = 0.0
    branch_scores: dict[str, float] = {}
    for name, result in branch_results:
        branch_scores[name] = result.score
        n_eff = float(result.components.get("n_eff") or 0.0)
        w = max(0.25, n_eff)
        weighted += result.score * w
        weight_sum += w
    score = round(weighted / weight_sum if weight_sum else PRIOR_SCORE, 1)
    dominant = max(branch_results, key=lambda item: float(item[1].components.get("n_eff") or 0))
    why = [
        "Company score is a credibility-weighted blend of branch scores.",
        f"{dominant[0]} dominates evidence (n_eff={dominant[1].components.get('n_eff')}).",
    ]
    return CompanyScoreResult(
        score=score,
        components={
            "algorithm_version": ALGORITHM_VERSION,
            "branch_scores": branch_scores,
            "why": why,
        },
    )


class ScoringEngine:
    """Load analyses from DB and persist score_v1 results."""

    def __init__(self, db):
        self.db = db

    async def score_branch(self, branch_id: int) -> BranchScoreResult:
        analyses = await self.db.list_branch_analyses(branch_id)
        result = compute_branch_score_v1(analyses)
        await self.db.insert_branch_score(
            branch_id,
            score=result.score,
            components=result.components,
            algorithm_version=ALGORITHM_VERSION,
        )
        return result

    async def score_company(self, company_id: int) -> CompanyScoreResult:
        branches = await self.db.list_company_branches(company_id, limit=10000)
        branch_results: list[tuple[str, BranchScoreResult]] = []
        for branch in branches:
            result = await self.score_branch(int(branch["id"]))
            branch_results.append((branch["name"], result))
        company = compute_company_score_v1(branch_results)
        await self.db.insert_company_score(
            company_id,
            score=company.score,
            components=company.components,
            algorithm_version=ALGORITHM_VERSION,
        )
        return company

    async def score_all_companies(self) -> list[dict[str, Any]]:
        companies = await self.db.list_companies(limit=100000)
        out = []
        for company in companies:
            result = await self.score_company(int(company["id"]))
            out.append(
                {
                    "company_id": company["id"],
                    "name": company["name"],
                    "score": result.score,
                }
            )
        return out
