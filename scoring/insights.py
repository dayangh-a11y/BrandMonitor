from __future__ import annotations

from collections import Counter
from typing import Any

from core.logging_setup import get_logger

log = get_logger("scoring")


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def build_insights_from_analyses(
    analyses: list[dict[str, Any]],
    *,
    scope_name: str,
) -> dict[str, Any]:
    usable = [a for a in analyses if (a.get("status") or "succeeded") == "succeeded"]
    complaints: Counter[str] = Counter()
    positives: Counter[str] = Counter()
    sentiments: Counter[str] = Counter()
    for row in usable:
        sentiments[str(row.get("sentiment") or "Neutral")] += 1
        for cat in _as_list(row.get("complaint_categories")):
            complaints[cat] += 1
        for cat in _as_list(row.get("positive_categories")):
            positives[cat] += 1

    pros = [c for c, _ in positives.most_common(5)]
    cons = [c for c, _ in complaints.most_common(5)]
    common = [c for c, _ in (complaints + positives).most_common(5)]
    n = len(usable)
    if n == 0:
        summary = f"{scope_name}: no successful analyses yet."
    else:
        top_sent = sentiments.most_common(1)[0][0]
        complaint_txt = ", ".join(cons[:3]) if cons else "none dominant"
        positive_txt = ", ".join(pros[:3]) if pros else "limited praise"
        summary = (
            f"{scope_name} shows mostly {top_sent.lower()} feedback across {n} analyzed reviews. "
            f"Frequent complaints: {complaint_txt}. Positive notes: {positive_txt}."
        )
    log.info("insights_built scope=%s n=%s", scope_name, n)
    return {
        "summary": summary,
        "pros": pros,
        "cons": cons,
        "common_categories": common,
        "review_count_used": n,
    }


class InsightsGenerator:
    def __init__(self, db):
        self.db = db

    async def refresh_branch(self, branch_id: int, *, branch_name: str = "") -> dict[str, Any]:
        analyses = await self.db.list_branch_analyses(branch_id)
        name = branch_name or f"Branch {branch_id}"
        payload = build_insights_from_analyses(analyses, scope_name=name)
        await self.db.upsert_branch_insights(
            branch_id,
            summary=payload["summary"],
            pros=payload["pros"],
            cons=payload["cons"],
            common_categories=payload["common_categories"],
            review_count_used=payload["review_count_used"],
            model_name="insights_v1",
            prompt_version="v1",
        )
        return payload

    async def refresh_company(self, company_id: int, *, company_name: str = "") -> dict[str, Any]:
        branches = await self.db.list_company_branches(company_id, limit=10000)
        all_analyses: list[dict[str, Any]] = []
        for branch in branches:
            await self.refresh_branch(int(branch["id"]), branch_name=branch["name"])
            all_analyses.extend(await self.db.list_branch_analyses(int(branch["id"])))
        name = company_name or f"Company {company_id}"
        payload = build_insights_from_analyses(all_analyses, scope_name=name)
        await self.db.upsert_company_insights(
            company_id,
            summary=payload["summary"],
            pros=payload["pros"],
            cons=payload["cons"],
            common_categories=payload["common_categories"],
            review_count_used=payload["review_count_used"],
            model_name="insights_v1",
            prompt_version="v1",
        )
        return payload
