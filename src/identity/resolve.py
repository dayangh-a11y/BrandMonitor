"""Resolve race-card / query attributes → permanent horse_id.

Future lookups must use horse_id, never horse_name as a join key.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.identity.load import load_horse_profiles
from src.identity.models import IdHorse, IdHorseAlias, IdHorseLink
from src.identity.normalize import name_similarity, normalize_name
from src.identity.profile import HorseProfile, HorseQuery
from src.identity.score import LOOKUP_THRESHOLD, score_query
from src.warehouse.models import WhHorse


@dataclass
class ResolveHit:
    horse_id: int
    display_name: str
    warehouse_horse_id: int | None
    score: float
    decision: str
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "horse_id": self.horse_id,
            "display_name": self.display_name,
            "warehouse_horse_id": self.warehouse_horse_id,
            "score": round(self.score, 4),
            "decision": self.decision,
            "evidence": self.evidence,
        }


def horse_id_for_warehouse(session: Session, warehouse_horse_id: int) -> int | None:
    link = session.scalar(
        select(IdHorseLink).where(IdHorseLink.warehouse_horse_id == warehouse_horse_id)
    )
    if link:
        return link.horse_id
    # Fallback: warehouse canonical pointer written by identity build
    wh = session.get(WhHorse, warehouse_horse_id)
    if wh and wh.canonical_entity_id:
        ent = session.get(IdHorse, wh.canonical_entity_id)
        if ent and ent.status == "active":
            return ent.horse_id
    return None


def warehouse_ids_for_horse(session: Session, horse_id: int) -> list[int]:
    rows = session.scalars(
        select(IdHorseLink.warehouse_horse_id).where(IdHorseLink.horse_id == horse_id)
    ).all()
    return [int(x) for x in rows]


def get_horse(session: Session, horse_id: int) -> IdHorse | None:
    row = session.get(IdHorse, horse_id)
    if row is None:
        return None
    if row.status == "merged" and row.merged_into_id:
        return session.get(IdHorse, row.merged_into_id)
    return row


def resolve_horse(
    session: Session,
    query: HorseQuery,
    *,
    limit: int = 5,
    min_score: float = LOOKUP_THRESHOLD,
    profiles: list[HorseProfile] | None = None,
) -> list[ResolveHit]:
    """
    Resolve a multi-signal query to permanent horse_id(s).

    Prefer source_horse_id link when present, then multi-signal scoring.
    Never uses raw exact string equality as the sole decision.
    """
    hits: list[ResolveHit] = []

    # 1) Strong path: source id → link
    if query.source_horse_id:
        link = session.scalar(
            select(IdHorseLink).where(
                IdHorseLink.source_horse_id == str(query.source_horse_id)
            )
        )
        if link:
            horse = get_horse(session, link.horse_id)
            if horse:
                hits.append(
                    ResolveHit(
                        horse_id=horse.horse_id,
                        display_name=horse.display_name,
                        warehouse_horse_id=link.warehouse_horse_id,
                        score=0.99,
                        decision="source_id",
                        evidence={"source_horse_id": query.source_horse_id},
                    )
                )
                return hits

    # 2) Multi-signal against profiles
    profs = profiles if profiles is not None else load_horse_profiles(session)
    scored: list[tuple[float, HorseProfile, dict[str, Any]]] = []
    q_name = normalize_name(query.name)
    for p in profs:
        # Cheap filter: require some name overlap unless source id already handled
        if q_name and name_similarity(query.name, p.name) < 0.55:
            continue
        result = score_query(query, p)
        if result.total_score < min_score:
            continue
        scored.append((result.total_score, p, result.to_dict()))

    scored.sort(key=lambda x: -x[0])

    seen_horse_ids: set[int] = set()
    for score, profile, evidence in scored[: max(limit * 3, limit)]:
        horse_id = horse_id_for_warehouse(session, profile.warehouse_horse_id)
        if horse_id is None:
            # Identity not built yet — synthesize provisional response with warehouse id
            # but do not invent a permanent id.
            continue
        if horse_id in seen_horse_ids:
            continue
        seen_horse_ids.add(horse_id)
        horse = get_horse(session, horse_id)
        if horse is None:
            continue
        hits.append(
            ResolveHit(
                horse_id=horse.horse_id,
                display_name=horse.display_name,
                warehouse_horse_id=profile.warehouse_horse_id,
                score=score,
                decision=evidence.get("decision", "candidate"),
                evidence=evidence,
            )
        )
        if len(hits) >= limit:
            break

    return hits


def resolve_horse_id(
    session: Session,
    *,
    name: str | None = None,
    sire: str | None = None,
    dam: str | None = None,
    age: int | None = None,
    sex: str | None = None,
    owner: str | None = None,
    trainer: str | None = None,
    source_horse_id: str | None = None,
) -> int | None:
    """Convenience: best permanent horse_id or None."""
    hits = resolve_horse(
        session,
        HorseQuery(
            name=name,
            sire=sire,
            dam=dam,
            age=age,
            sex=sex,
            owner=owner,
            trainer=trainer,
            source_horse_id=source_horse_id,
        ),
        limit=1,
    )
    return hits[0].horse_id if hits else None
