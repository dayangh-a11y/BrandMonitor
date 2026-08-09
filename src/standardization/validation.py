"""Module 10 — Validation Engine.

Detect suspicious rankings and return warnings.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.analytics.models import AnlHorseMetrics, AnlRanking
from src.standardization.constants import DEFAULT_MIN_STARTS


def validate_metrics_row(row: AnlHorseMetrics) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    starts = int(row.starts or 0)

    if starts == 1:
        warnings.append(
            {
                "code": "single_start",
                "severity": "warning",
                "message": f"Horse {row.horse_name} has only one race",
                "horse_id": row.horse_id,
            }
        )

    # Impossible statistics
    if starts > 0:
        if (row.wins or 0) > starts:
            warnings.append(
                {
                    "code": "impossible_wins",
                    "severity": "error",
                    "message": f"wins={row.wins} > starts={starts}",
                    "horse_id": row.horse_id,
                }
            )
        if row.win_rate is not None and not (0.0 <= row.win_rate <= 1.0 + 1e-9):
            warnings.append(
                {
                    "code": "impossible_win_rate",
                    "severity": "error",
                    "message": f"win_rate={row.win_rate} out of [0,1]",
                    "horse_id": row.horse_id,
                }
            )
        if row.avg_finish is not None and row.avg_finish < 1:
            warnings.append(
                {
                    "code": "impossible_avg_finish",
                    "severity": "error",
                    "message": f"avg_finish={row.avg_finish} < 1",
                    "horse_id": row.horse_id,
                }
            )
        if (
            starts == 1
            and row.win_rate == 1.0
            and row.place_rate == 1.0
            and (row.avg_finish or 0) == 1
        ):
            warnings.append(
                {
                    "code": "perfect_single_start",
                    "severity": "warning",
                    "message": (
                        "All major rates are perfect on 1 start — "
                        "not valid for Season Best"
                    ),
                    "horse_id": row.horse_id,
                }
            )

    # Missing data
    missing_fields = []
    for field in ("performance_rating", "consistency_score", "form_score_5"):
        if getattr(row, field, None) is None and starts >= DEFAULT_MIN_STARTS:
            missing_fields.append(field)
    if missing_fields:
        warnings.append(
            {
                "code": "missing_data",
                "severity": "warning",
                "message": f"Missing fields: {', '.join(missing_fields)}",
                "horse_id": row.horse_id,
            }
        )

    # Abnormal earnings: huge earnings with 1 start vs peers handled at batch level
    if starts == 1 and (row.earnings_total or 0) > 0:
        warnings.append(
            {
                "code": "earnings_single_start",
                "severity": "info",
                "message": (
                    f"Earnings {row.earnings_total} on a single start — "
                    "do not use for Performance Ranking"
                ),
                "horse_id": row.horse_id,
            }
        )

    return warnings


def validate_rankings(
    session: Session,
    *,
    scope: str = "season",
    season_key: str | None = None,
) -> dict[str, Any]:
    q = select(AnlHorseMetrics).where(AnlHorseMetrics.scope == scope)
    if season_key:
        q = q.where(AnlHorseMetrics.season_key == season_key)
    rows = list(session.scalars(q).all())

    all_warnings: list[dict[str, Any]] = []
    for row in rows:
        all_warnings.extend(validate_metrics_row(row))

    # Abnormal earnings: z-like check within scope
    earnings = [float(r.earnings_total or 0) for r in rows if (r.earnings_total or 0) > 0]
    if len(earnings) >= 5:
        mean_e = sum(earnings) / len(earnings)
        var = sum((e - mean_e) ** 2 for e in earnings) / len(earnings)
        std = var**0.5
        if std > 0:
            for r in rows:
                e = float(r.earnings_total or 0)
                if e > mean_e + 4 * std and (r.starts or 0) <= 2:
                    all_warnings.append(
                        {
                            "code": "abnormal_earnings",
                            "severity": "warning",
                            "message": (
                                f"Abnormal earnings {e} (mean={mean_e:.1f}, "
                                f"std={std:.1f}) with starts={r.starts}"
                            ),
                            "horse_id": r.horse_id,
                        }
                    )

    # Rankings that include single-start horses on performance boards
    perf_boards = {
        "best_season",
        "most_successful",
        "highest_win_rate",
        "best_form",
        "most_consistent",
    }
    ranking_q = select(AnlRanking).where(AnlRanking.category.in_(perf_boards))
    if season_key:
        ranking_q = ranking_q.where(AnlRanking.season_key == season_key)
    for rank in session.scalars(ranking_q).all():
        why = rank.why_json or {}
        starts = why.get("starts", rank.starts)
        if starts is not None and int(starts) < DEFAULT_MIN_STARTS and rank.category != "highest_earnings":
            all_warnings.append(
                {
                    "code": "underqualified_on_board",
                    "severity": "error",
                    "message": (
                        f"Board {rank.category} ranks entity with starts={starts} "
                        f"< minimum_starts={DEFAULT_MIN_STARTS}"
                    ),
                    "entity_id": rank.entity_id,
                    "board": rank.category,
                }
            )

    by_code: dict[str, int] = {}
    for w in all_warnings:
        by_code[w["code"]] = by_code.get(w["code"], 0) + 1

    return {
        "module": "validation_engine",
        "rows_analyzed": len(rows),
        "warnings_total": len(all_warnings),
        "warnings_by_code": by_code,
        "warnings": all_warnings[:500],
        "status": "error"
        if any(w["severity"] == "error" for w in all_warnings)
        else ("warning" if all_warnings else "ok"),
    }
