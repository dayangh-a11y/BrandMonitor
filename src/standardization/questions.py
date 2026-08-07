"""Module 9 — Question Engine.

Natural language / slug question → Analytics Rule → SQL → Metrics → Explanation.
Never answer directly without this pipeline.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.standardization.audit import write_audit
from src.standardization.confidence import compute_confidence
from src.standardization.constants import PLATFORM_VERSION
from src.standardization.explain import Explanation, build_explanation
from src.standardization.ranking_contracts import RANKING_CONTRACTS, get_contract


@dataclass(frozen=True, slots=True)
class QuestionRule:
    rule_id: str
    aliases: tuple[str, ...]
    sql: str
    metrics: tuple[str, ...]
    board: str | None = None
    formula: str = ""
    description: str = ""


QUESTION_RULES: list[QuestionRule] = [
    QuestionRule(
        rule_id="Q_SEASON_BEST",
        aliases=("best_season", "best horse of the season", "بهترین اسب فصل", "season best"),
        sql="SELECT * FROM anl_v_best_horses_season ORDER BY rank LIMIT :n",
        metrics=("performance", "wins", "consistency", "form"),
        board="best_season",
        formula="performance_rating DESC with eligibility gate",
        description="Season Best Horse ranking",
    ),
    QuestionRule(
        rule_id="Q_SEASON_BEST_STATUS",
        aliases=("season_best_status", "insufficient data", "وضعیت بهترین فصل"),
        sql="SELECT * FROM anl_v_season_best_status",
        metrics=("starts",),
        board="best_season",
        formula="season_best_gate(starts_list, minimum_starts)",
        description="Season Best availability gate",
    ),
    QuestionRule(
        rule_id="Q_MOST_SUCCESSFUL",
        aliases=("most_successful", "most wins", "موفق‌ترین"),
        sql="SELECT * FROM anl_v_most_successful_horses ORDER BY rank LIMIT :n",
        metrics=("wins",),
        board="most_successful",
        formula="wins DESC",
        description="Most Successful Horse",
    ),
    QuestionRule(
        rule_id="Q_HIGHEST_EARNINGS",
        aliases=("highest_earnings", "top earnings", "بیشترین جایزه"),
        sql="SELECT * FROM anl_v_highest_earnings_horses ORDER BY rank LIMIT :n",
        metrics=("earnings",),
        board="highest_earnings",
        formula="earnings_total DESC",
        description="Highest Earnings Horse",
    ),
    QuestionRule(
        rule_id="Q_HIGHEST_WIN_RATE",
        aliases=("highest_win_rate", "best win rate", "بهترین درصد برد"),
        sql="SELECT * FROM anl_v_highest_win_rate_horses ORDER BY rank LIMIT :n",
        metrics=("wins", "top2_rate"),
        board="highest_win_rate",
        formula="win_rate DESC",
        description="Highest Win Rate Horse",
    ),
    QuestionRule(
        rule_id="Q_BEST_FORM",
        aliases=("best_form", "form", "بهترین فرم"),
        sql="SELECT * FROM anl_v_best_form_horses ORDER BY rank LIMIT :n",
        metrics=("form",),
        board="best_form",
        formula="form_score_5 DESC",
        description="Best Form Horse",
    ),
    QuestionRule(
        rule_id="Q_MOST_CONSISTENT",
        aliases=("most_consistent", "consistency", "پایدارترین"),
        sql="SELECT * FROM anl_v_most_consistent_horses ORDER BY rank LIMIT :n",
        metrics=("consistency",),
        board="most_consistent",
        formula="consistency_score DESC",
        description="Most Consistent Horse",
    ),
    QuestionRule(
        rule_id="Q_BEST_MARE",
        aliases=("best_mare", "best filly", "بهترین مادیان"),
        sql="SELECT * FROM anl_v_best_mare ORDER BY rank LIMIT :n",
        metrics=("sex_adjusted_performance_rating",),
        board="best_mare",
        formula="sex_adjusted_performance_rating DESC (Mare/Filly)",
        description="Best Mare",
    ),
    QuestionRule(
        rule_id="Q_BEST_STALLION",
        aliases=("best_stallion", "best colt", "بهترین نریان"),
        sql="SELECT * FROM anl_v_best_stallion ORDER BY rank LIMIT :n",
        metrics=("sex_adjusted_performance_rating",),
        board="best_stallion",
        formula="sex_adjusted_performance_rating DESC (Stallion/Colt)",
        description="Best Stallion",
    ),
    QuestionRule(
        rule_id="Q_BEST_MIXED",
        aliases=("best_mixed_race_performer", "best mixed", "بهترین مختلط"),
        sql="SELECT * FROM anl_v_best_mixed_race_performer ORDER BY rank LIMIT :n",
        metrics=("mixed_race_performance",),
        board="best_mixed_race_performer",
        formula="mixed_race_performance DESC",
        description="Best Mixed-Race Performer",
    ),
    QuestionRule(
        rule_id="Q_FEMALE_VS_MALES",
        aliases=(
            "best_female_against_males",
            "best female against males",
            "بهترین ماده مقابل نر",
        ),
        sql="SELECT * FROM anl_v_best_female_against_males ORDER BY rank LIMIT :n",
        metrics=("performance_vs_males",),
        board="best_female_against_males",
        formula="performance_vs_males DESC",
        description="Best Female Against Males",
    ),
    QuestionRule(
        rule_id="Q_DOMINANT_MALE",
        aliases=("most_dominant_male", "dominant male", "مسلط‌ترین نر"),
        sql="SELECT * FROM anl_v_most_dominant_male ORDER BY rank LIMIT :n",
        metrics=("sex_adjusted_performance_rating",),
        board="most_dominant_male",
        formula="sex_adjusted_performance_rating DESC (males)",
        description="Most Dominant Male",
    ),
]


def _norm_q(q: str) -> str:
    text = re.sub(r"\s+", " ", (q or "").strip().lower())
    return text.replace("_", " ")


def resolve_question(question: str) -> QuestionRule | None:
    q = _norm_q(question)
    if not q:
        return None
    # Exact alias match first
    for rule in QUESTION_RULES:
        for alias in rule.aliases:
            if q == _norm_q(alias):
                return rule
    # Substring / containment
    for rule in QUESTION_RULES:
        for alias in rule.aliases:
            na = _norm_q(alias)
            if na and (na in q or q in na):
                return rule
    return None


def answer_question(
    session: Session,
    question: str,
    *,
    limit: int = 10,
    audit: bool = True,
) -> dict[str, Any]:
    """
    Full pipeline: question → rule → SQL → metrics → explanation.
    Never returns a bare opinion without rule metadata.
    """
    started = time.perf_counter()
    rule = resolve_question(question)
    if rule is None:
        expl = build_explanation(
            rule="UNMAPPED_QUESTION",
            formula="n/a",
            metrics={},
            rows_analyzed=0,
            confidence=compute_confidence(starts=0, completeness=0.0),
            missing_data=["question_mapping"],
            warnings=[f"No analytics rule mapped for: {question!r}"],
            version=PLATFORM_VERSION,
        )
        result = {
            "status": "unmapped",
            "question": question,
            "rule_id": None,
            "sql": None,
            "rows": [],
            "explanation": expl.to_dict(),
            "explanation_text": expl.to_text(),
        }
        if audit:
            write_audit(
                session,
                question=question,
                rule_id="UNMAPPED_QUESTION",
                rows_analyzed=0,
                execution_time_ms=(time.perf_counter() - started) * 1000,
                result_summary="unmapped",
                confidence="very_low",
            )
        return result

    contract = get_contract(rule.board) if rule.board else None
    rows = session.execute(text(rule.sql), {"n": limit}).mappings().all()
    row_dicts = [dict(r) for r in rows]

    # Aggregate confidence from first rows' why_json when present
    starts_vals = []
    missing = []
    warnings: list[str] = []
    for rd in row_dicts:
        why = rd.get("why_json") or {}
        if isinstance(why, str):
            import json

            try:
                why = json.loads(why)
            except Exception:  # noqa: BLE001
                why = {}
        if isinstance(why, dict) and why.get("starts") is not None:
            starts_vals.append(int(why["starts"]))
        if rd.get("status") == "INSUFFICIENT_DATA" or (
            isinstance(why, dict) and why.get("qualification_status") == "insufficient_data"
        ):
            warnings.append("INSUFFICIENT DATA for Season Best")

    avg_starts = int(sum(starts_vals) / len(starts_vals)) if starts_vals else 0
    conf = compute_confidence(
        starts=avg_starts,
        missing_rate=0.0 if row_dicts else 1.0,
        completeness=1.0 if row_dicts else 0.0,
    )
    if not row_dicts:
        missing.append("leaderboard_rows")
        warnings.append("No rows — run analytics build / standardization first")

    formula = rule.formula
    if contract:
        formula = (
            f"{contract.ranking_formula}; tie_break={list(contract.tie_break)}; "
            f"min_starts={contract.minimum_starts}"
        )

    expl = build_explanation(
        rule=rule.rule_id,
        formula=formula,
        metrics={m: True for m in rule.metrics},
        rows_analyzed=len(row_dicts),
        confidence=conf,
        missing_data=missing,
        warnings=warnings,
        version=(contract.version if contract else PLATFORM_VERSION),
        board=rule.board,
        contract=contract.to_dict() if contract else None,
        description=rule.description,
    )

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    result = {
        "status": "ok",
        "question": question,
        "rule_id": rule.rule_id,
        "sql": rule.sql,
        "board": rule.board,
        "contract": contract.to_dict() if contract else None,
        "rows": row_dicts,
        "explanation": expl.to_dict(),
        "explanation_text": expl.to_text(),
        "execution_time_ms": round(elapsed_ms, 3),
        "version": PLATFORM_VERSION,
    }
    if audit:
        write_audit(
            session,
            question=question,
            rule_id=rule.rule_id,
            sql_text=rule.sql,
            rows_analyzed=len(row_dicts),
            execution_time_ms=elapsed_ms,
            confidence=conf.band,
            result_summary=expl.to_text(),
            payload={"board": rule.board, "limit": limit},
        )
    return result


def list_question_rules() -> list[dict[str, Any]]:
    return [
        {
            "rule_id": r.rule_id,
            "aliases": list(r.aliases),
            "sql": r.sql,
            "metrics": list(r.metrics),
            "board": r.board,
            "description": r.description,
        }
        for r in QUESTION_RULES
    ]
