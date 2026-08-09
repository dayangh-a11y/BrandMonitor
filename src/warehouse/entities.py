"""Entity resolution — detect duplicate horses / people with fuzzy support."""

from __future__ import annotations

from collections import defaultdict

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.warehouse.fuzzy import find_duplicate_pairs, normalize_name, similarity
from src.warehouse.models import (
    WhEntityMatch,
    WhHorse,
    WhJockey,
    WhOwner,
    WhTrainer,
)


def _upsert_match(
    session: Session,
    *,
    entity_type: str,
    left: str,
    right: str,
    score: float,
    method: str,
) -> None:
    a, b = sorted([left, right])
    existing = session.scalar(
        select(WhEntityMatch).where(
            WhEntityMatch.entity_type == entity_type,
            WhEntityMatch.left_key == a,
            WhEntityMatch.right_key == b,
        )
    )
    if existing:
        existing.score = score
        existing.method = method
        return
    session.add(
        WhEntityMatch(
            entity_type=entity_type,
            left_key=a,
            right_key=b,
            score=score,
            method=method,
            status="candidate",
        )
    )


def resolve_people(session: Session, *, threshold: float = 0.92) -> dict[str, int]:
    counts = {"jockey": 0, "trainer": 0, "owner": 0}
    for entity_type, model in (
        ("jockey", WhJockey),
        ("trainer", WhTrainer),
        ("owner", WhOwner),
    ):
        names = list(session.scalars(select(model.name)).all())
        # Exact normalized duplicates
        buckets: dict[str, list[str]] = defaultdict(list)
        for name in names:
            buckets[normalize_name(name)].append(name)
        for group in buckets.values():
            if len(group) > 1:
                for i, left in enumerate(group):
                    for right in group[i + 1 :]:
                        _upsert_match(
                            session,
                            entity_type=entity_type,
                            left=left,
                            right=right,
                            score=1.0,
                            method="exact_normalized",
                        )
                        counts[entity_type] += 1
        # Fuzzy
        for left, right, score in find_duplicate_pairs(names, threshold=threshold):
            if normalize_name(left) == normalize_name(right):
                continue
            _upsert_match(
                session,
                entity_type=entity_type,
                left=left,
                right=right,
                score=score,
                method="fuzzy",
            )
            counts[entity_type] += 1
    session.flush()
    logger.info("Entity resolution people matches={}", counts)
    return counts


def resolve_horses(session: Session, *, threshold: float = 0.95) -> int:
    horses = session.scalars(select(WhHorse)).all()
    # Exact source id already unique; detect name collisions across ids
    by_name: dict[str, list[WhHorse]] = defaultdict(list)
    for h in horses:
        by_name[normalize_name(h.name)].append(h)

    count = 0
    for group in by_name.values():
        if len(group) < 2:
            continue
        for i, left in enumerate(group):
            for right in group[i + 1 :]:
                # Same normalized name, different source ids → duplicate candidate
                if left.source_horse_id and left.source_horse_id == right.source_horse_id:
                    continue
                score = similarity(left.name, right.name)
                if score < threshold:
                    continue
                key_l = left.source_horse_id or f"wh:{left.id}"
                key_r = right.source_horse_id or f"wh:{right.id}"
                _upsert_match(
                    session,
                    entity_type="horse",
                    left=key_l,
                    right=key_r,
                    score=score,
                    method="name_collision",
                )
                count += 1

    # Fuzzy across distinct names
    names = [h.name for h in horses]
    id_by_name = {normalize_name(h.name): (h.source_horse_id or f"wh:{h.id}") for h in horses}
    for left, right, score in find_duplicate_pairs(names, threshold=threshold):
        kl = id_by_name.get(normalize_name(left))
        kr = id_by_name.get(normalize_name(right))
        if not kl or not kr or kl == kr:
            continue
        _upsert_match(
            session,
            entity_type="horse",
            left=kl,
            right=kr,
            score=score,
            method="fuzzy",
        )
        count += 1

    session.flush()
    logger.info("Entity resolution horse match candidates={}", count)
    return count


def run_entity_resolution(session: Session, *, threshold: float = 0.92) -> dict[str, int]:
    people = resolve_people(session, threshold=threshold)
    horses = resolve_horses(session, threshold=max(threshold, 0.95))
    return {**people, "horse": horses}
