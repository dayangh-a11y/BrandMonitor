"""Module 2 — Entity Resolution.

Normalize names for Horse, Trainer, Jockey, Owner, Sire, Stable, Track.
Every entity gets a permanent ID. Never rely on names alone.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.standardization.models import StdEntity, StdEntityAlias
from src.warehouse.fuzzy import normalize_name
from src.warehouse.models import (
    WhHorse,
    WhHorsePedigree,
    WhJockey,
    WhOwner,
    WhRace,
    WhTrainer,
)

ENTITY_TYPES = ("horse", "trainer", "jockey", "owner", "sire", "stable", "track")


def _upsert_entity(
    session: Session,
    *,
    entity_type: str,
    display_name: str,
    warehouse_id: int | None = None,
    source_key: str | None = None,
    meta: dict[str, Any] | None = None,
) -> StdEntity:
    norm = normalize_name(display_name)
    if not norm:
        raise ValueError(f"Cannot create entity with empty name ({entity_type})")

    existing = session.scalar(
        select(StdEntity).where(
            StdEntity.entity_type == entity_type,
            StdEntity.normalized_key == norm,
        )
    )
    if existing:
        if warehouse_id is not None and existing.warehouse_id is None:
            existing.warehouse_id = warehouse_id
        if source_key and not existing.source_key:
            existing.source_key = source_key
        if display_name and existing.display_name != display_name:
            # Keep canonical display; add alias for variant
            _ensure_alias(
                session,
                entity_id=existing.id,
                entity_type=entity_type,
                alias=display_name,
                method="display_variant",
            )
        if meta:
            merged = dict(existing.meta_json or {})
            merged.update(meta)
            existing.meta_json = merged
        return existing

    row = StdEntity(
        entity_type=entity_type,
        display_name=display_name.strip(),
        normalized_key=norm,
        warehouse_id=warehouse_id,
        source_key=source_key,
        meta_json=meta,
    )
    session.add(row)
    session.flush()
    _ensure_alias(
        session,
        entity_id=row.id,
        entity_type=entity_type,
        alias=display_name,
        method="canonical",
    )
    return row


def _ensure_alias(
    session: Session,
    *,
    entity_id: int,
    entity_type: str,
    alias: str,
    method: str,
) -> None:
    norm = normalize_name(alias)
    if not norm:
        return
    existing = session.scalar(
        select(StdEntityAlias).where(
            StdEntityAlias.entity_type == entity_type,
            StdEntityAlias.normalized_alias == norm,
        )
    )
    if existing:
        return
    session.add(
        StdEntityAlias(
            entity_id=entity_id,
            entity_type=entity_type,
            alias=alias.strip(),
            normalized_alias=norm,
            method=method,
        )
    )


def resolve_entity_id(
    session: Session,
    *,
    entity_type: str,
    name: str | None,
) -> int | None:
    """Look up permanent ID by name — prefer ID, never trust name for joins."""
    norm = normalize_name(name)
    if not norm:
        return None
    alias = session.scalar(
        select(StdEntityAlias).where(
            StdEntityAlias.entity_type == entity_type,
            StdEntityAlias.normalized_alias == norm,
        )
    )
    if alias:
        return alias.entity_id
    ent = session.scalar(
        select(StdEntity).where(
            StdEntity.entity_type == entity_type,
            StdEntity.normalized_key == norm,
        )
    )
    return ent.id if ent else None


def apply_canonical_ids_to_warehouse(session: Session) -> dict[str, int]:
    """Write std entity ids onto warehouse canonical_entity_id columns."""
    updated = {"horse": 0, "jockey": 0, "trainer": 0, "owner": 0}
    for entity_type, model in (
        ("horse", WhHorse),
        ("jockey", WhJockey),
        ("trainer", WhTrainer),
        ("owner", WhOwner),
    ):
        for row in session.scalars(select(model)).all():
            ent = session.scalar(
                select(StdEntity).where(
                    StdEntity.entity_type == entity_type,
                    StdEntity.warehouse_id == row.id,
                )
            )
            if ent is None:
                ent_id = resolve_entity_id(session, entity_type=entity_type, name=row.name)
                if ent_id is None:
                    continue
                ent = session.get(StdEntity, ent_id)
            if ent and row.canonical_entity_id != ent.id:
                row.canonical_entity_id = ent.id
                updated[entity_type] += 1
    session.flush()
    return updated


def build_entity_registry(session: Session) -> dict[str, int]:
    """Normalize all known entities into permanent IDs."""
    counts = {t: 0 for t in ENTITY_TYPES}

    for h in session.scalars(select(WhHorse)).all():
        _upsert_entity(
            session,
            entity_type="horse",
            display_name=h.name,
            warehouse_id=h.id,
            source_key=h.source_horse_id,
            meta={"source": h.source},
        )
        counts["horse"] += 1

    for j in session.scalars(select(WhJockey)).all():
        _upsert_entity(session, entity_type="jockey", display_name=j.name, warehouse_id=j.id)
        counts["jockey"] += 1

    for t in session.scalars(select(WhTrainer)).all():
        _upsert_entity(session, entity_type="trainer", display_name=t.name, warehouse_id=t.id)
        counts["trainer"] += 1

    for o in session.scalars(select(WhOwner)).all():
        _upsert_entity(session, entity_type="owner", display_name=o.name, warehouse_id=o.id)
        counts["owner"] += 1

    # Sires from pedigree
    for ped in session.scalars(select(WhHorsePedigree)).all():
        if ped.sire_name and normalize_name(ped.sire_name):
            _upsert_entity(
                session,
                entity_type="sire",
                display_name=ped.sire_name,
                warehouse_id=ped.sire_horse_id,
            )
            counts["sire"] += 1

    # Tracks from races
    tracks: set[tuple[str, str]] = set()
    for r in session.scalars(select(WhRace)).all():
        code = r.racecourse_code or r.track
        label = r.track or r.racecourse_code
        if not label:
            continue
        key = (normalize_name(code), normalize_name(label))
        if key in tracks:
            continue
        tracks.add(key)
        _upsert_entity(
            session,
            entity_type="track",
            display_name=label,
            source_key=r.racecourse_code,
            meta={"racecourse_code": r.racecourse_code, "province": r.province},
        )
        counts["track"] += 1

    # Stable placeholder: owners often act as stables in this dataset — skip inventing
    session.flush()
    canon = apply_canonical_ids_to_warehouse(session)
    logger.info("Entity registry built {} canonical_updates={}", counts, canon)
    return {"entities": counts, "canonical_updates": canon}
