"""Durable canonical attribute corrections for horse identity.

Raw warehouse / source tables are never overwritten. Corrections apply only to
canonical `id_horses` fields and are recorded in `meta_json` for provenance.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.identity.models import IdHorse, IdHorseLink

DEFAULT_REGISTRY = Path("data/identity/birth_year_corrections.json")


def load_birth_year_corrections(path: Path | None = None) -> list[dict[str, Any]]:
    registry = path or DEFAULT_REGISTRY
    if not registry.exists():
        return []
    data = json.loads(registry.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected list in {registry}")
    return data


def _resolve_horse_id(session: Session, corr: dict[str, Any]) -> int | None:
    """Resolve target permanent horse_id via stable source id, then horse_id."""
    source_horse_id = corr.get("source_horse_id")
    if source_horse_id:
        link = session.execute(
            select(IdHorseLink).where(IdHorseLink.source_horse_id == str(source_horse_id))
        ).scalar_one_or_none()
        if link is not None:
            return int(link.horse_id)
    horse_id = corr.get("horse_id")
    if horse_id is not None:
        horse = session.get(IdHorse, int(horse_id))
        if horse is not None:
            return int(horse.horse_id)
    return None


def apply_birth_year_corrections(
    session: Session,
    *,
    path: Path | None = None,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """
    Apply registry corrections to canonical `id_horses.birth_year`.

    - Does NOT touch raw_horses / wh_horses birthdate or race results.
    - Stores provenance under meta_json['birth_year_correction'].
    """
    corrections = load_birth_year_corrections(path)
    applied: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()

    for corr in corrections:
        horse_id = _resolve_horse_id(session, corr)
        if horse_id is None:
            logger.warning(
                "birth_year correction skipped (horse not found): {}",
                corr.get("source_horse_id") or corr.get("horse_id"),
            )
            continue

        horse = session.get(IdHorse, horse_id)
        if horse is None:
            continue

        old_value = horse.birth_year
        new_value = int(corr["new_value"])
        meta = dict(horse.meta_json or {})
        # Preserve originally observed / inferred values for provenance
        if "birth_year_raw_observed" not in meta:
            meta["birth_year_raw_observed"] = old_value
        if "birth_years" in meta and "birth_years_raw_observed" not in meta:
            meta["birth_years_raw_observed"] = meta.get("birth_years")

        provenance = {
            "source": corr.get("source", "inferred_from_race_age_sequence"),
            "confidence": corr.get("confidence", "MEDIUM"),
            "evidence": corr.get("evidence"),
            "old_value": corr.get("old_value", old_value),
            "new_value": new_value,
            "previous_canonical_value": old_value,
            "applied_at_utc": now,
            "registry_source_horse_id": corr.get("source_horse_id"),
        }

        record = {
            "horse_id": horse_id,
            "display_name": horse.display_name,
            "old_value": old_value,
            "new_value": new_value,
            "changed": old_value != new_value,
            "dry_run": dry_run,
        }

        if dry_run:
            applied.append(record)
            continue

        horse.birth_year = new_value
        meta["birth_year_correction"] = provenance
        # Keep birth_years list informative but mark corrected canonical
        meta["birth_year_canonical"] = new_value
        horse.meta_json = meta
        session.add(horse)
        applied.append(record)
        logger.info(
            "canonical birth_year corrected horse_id={} {} → {} ({})",
            horse_id,
            old_value,
            new_value,
            provenance["source"],
        )

    if not dry_run and applied:
        session.flush()
        # Stamp registry applied_at (best-effort local file update)
        registry = path or DEFAULT_REGISTRY
        if registry.exists():
            data = load_birth_year_corrections(registry)
            by_source = {c.get("source_horse_id"): c for c in data}
            for corr in corrections:
                key = corr.get("source_horse_id")
                if key in by_source:
                    by_source[key]["applied_at_utc"] = now
            registry.parent.mkdir(parents=True, exist_ok=True)
            registry.write_text(
                json.dumps(list(by_source.values()) if by_source else data, ensure_ascii=False, indent=2)
                + "\n",
                encoding="utf-8",
            )

    return applied
