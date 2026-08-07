"""Duplicate horse + possible-merge report."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.identity.models import IdHorse, IdHorseLink, IdHorseMergeCandidate


def duplicate_merge_report(
    session: Session,
    *,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Report:
    - permanent IDs that already merged multiple warehouse rows
    - open merge candidates (possible merges)
    """
    links = list(session.scalars(select(IdHorseLink)).all())
    by_horse: dict[int, list[IdHorseLink]] = {}
    for link in links:
        by_horse.setdefault(link.horse_id, []).append(link)

    duplicates: list[dict[str, Any]] = []
    for horse_id, group in by_horse.items():
        if len(group) < 2:
            continue
        horse = session.get(IdHorse, horse_id)
        duplicates.append(
            {
                "horse_id": horse_id,
                "display_name": horse.display_name if horse else None,
                "warehouse_ids": [g.warehouse_horse_id for g in group],
                "source_horse_ids": [g.source_horse_id for g in group],
                "methods": [g.method for g in group],
                "member_names": (horse.meta_json or {}).get("member_names") if horse else None,
            }
        )
    duplicates.sort(key=lambda d: -len(d["warehouse_ids"]))

    open_count = session.scalar(
        select(func.count())
        .select_from(IdHorseMergeCandidate)
        .where(IdHorseMergeCandidate.status == "open")
    )
    open_rows = list(
        session.scalars(
            select(IdHorseMergeCandidate)
            .where(IdHorseMergeCandidate.status == "open")
            .order_by(IdHorseMergeCandidate.score.desc())
            .limit(limit)
        ).all()
    )
    possible_merges: list[dict[str, Any]] = []
    for row in open_rows:
        left = session.get(IdHorse, row.left_horse_id)
        right = session.get(IdHorse, row.right_horse_id)
        possible_merges.append(
            {
                "left_horse_id": row.left_horse_id,
                "right_horse_id": row.right_horse_id,
                "left_name": left.display_name if left else None,
                "right_name": right.display_name if right else None,
                "left_warehouse_id": row.left_warehouse_id,
                "right_warehouse_id": row.right_warehouse_id,
                "score": round(row.score, 4),
                "decision": row.decision,
                "evidence": row.evidence_json,
                "status": row.status,
            }
        )

    permanent_n = session.scalar(
        select(func.count()).select_from(IdHorse).where(IdHorse.status == "active")
    )
    warehouse_n = session.scalar(select(func.count()).select_from(IdHorseLink))

    return {
        "summary": {
            "permanent_horse_ids": int(permanent_n or 0),
            "warehouse_links": int(warehouse_n or 0),
            "duplicate_clusters": len(duplicates),
            "open_merge_candidates": int(open_count or 0),
            "open_merge_candidates_shown": len(possible_merges),
        },
        "duplicate_horses": duplicates[:limit],
        "possible_merges": possible_merges,
    }


def format_duplicate_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    s = report["summary"]
    lines.append("=== Horse Identity — Duplicate / Merge Report ===")
    lines.append(
        f"permanent_ids={s['permanent_horse_ids']}  "
        f"warehouse_links={s['warehouse_links']}  "
        f"duplicate_clusters={s['duplicate_clusters']}  "
        f"open_candidates={s['open_merge_candidates']}"
    )
    lines.append("")
    lines.append("--- Already merged duplicates (one horse_id, many warehouse rows) ---")
    dups = report["duplicate_horses"]
    if not dups:
        lines.append("(none)")
    for d in dups[:50]:
        names = ", ".join(d.get("member_names") or [])
        lines.append(
            f"horse_id={d['horse_id']}  display={d['display_name']!r}  "
            f"warehouse_ids={d['warehouse_ids']}  names=[{names}]"
        )
    lines.append("")
    lines.append("--- Possible merges (review) ---")
    merges = report["possible_merges"]
    if not merges:
        lines.append("(none)")
    for m in merges[:50]:
        lines.append(
            f"score={m['score']:.3f}  "
            f"{m['left_horse_id']}:{m['left_name']!r}  ↔  "
            f"{m['right_horse_id']}:{m['right_name']!r}  "
            f"wh=({m['left_warehouse_id']},{m['right_warehouse_id']})"
        )
        ev = m.get("evidence") or {}
        signals = ev.get("signals") or []
        if signals:
            parts = [
                f"{x['signal']}={x['score']}"
                for x in signals
                if x.get("score") is not None
            ]
            lines.append("    signals: " + ", ".join(parts))
    return "\n".join(lines)
