"""Module 12 — Version Control for metrics, rules, weights, formulas, queries."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.standardization.constants import MODULES, PLATFORM_VERSION
from src.standardization.metrics_catalog import METRIC_DEFINITIONS
from src.standardization.models import StdVersionRegistry
from src.standardization.ranking_contracts import RANKING_CONTRACTS


def register_artifact(
    session: Session,
    *,
    artifact_type: str,
    artifact_name: str,
    version: str,
    definition: dict[str, Any] | None = None,
    set_current: bool = True,
) -> StdVersionRegistry:
    existing = session.scalar(
        select(StdVersionRegistry).where(
            StdVersionRegistry.artifact_type == artifact_type,
            StdVersionRegistry.artifact_name == artifact_name,
            StdVersionRegistry.version == version,
        )
    )
    if existing:
        if set_current and not existing.is_current:
            session.execute(
                update(StdVersionRegistry)
                .where(
                    StdVersionRegistry.artifact_type == artifact_type,
                    StdVersionRegistry.artifact_name == artifact_name,
                )
                .values(is_current=False)
            )
            existing.is_current = True
        if definition is not None:
            existing.definition_json = definition
        return existing

    if set_current:
        session.execute(
            update(StdVersionRegistry)
            .where(
                StdVersionRegistry.artifact_type == artifact_type,
                StdVersionRegistry.artifact_name == artifact_name,
            )
            .values(is_current=False)
        )

    row = StdVersionRegistry(
        artifact_type=artifact_type,
        artifact_name=artifact_name,
        version=version,
        definition_json=definition,
        is_current=set_current,
    )
    session.add(row)
    session.flush()
    return row


def seed_version_registry(session: Session) -> dict[str, int]:
    """Register current platform artifacts so rankings are reproducible."""
    counts = {"modules": 0, "metrics": 0, "rankings": 0, "platform": 0}

    register_artifact(
        session,
        artifact_type="platform",
        artifact_name="standardization",
        version=PLATFORM_VERSION,
        definition={"modules": list(MODULES.keys())},
    )
    counts["platform"] = 1

    for key, meta in MODULES.items():
        register_artifact(
            session,
            artifact_type="module",
            artifact_name=key,
            version=meta["version"],
            definition=meta,
        )
        counts["modules"] += 1

    for name, defn in METRIC_DEFINITIONS.items():
        register_artifact(
            session,
            artifact_type="metric",
            artifact_name=name,
            version=defn.version,
            definition=defn.to_dict(),
        )
        counts["metrics"] += 1

    for name, contract in RANKING_CONTRACTS.items():
        register_artifact(
            session,
            artifact_type="ranking",
            artifact_name=name,
            version=contract.version,
            definition=contract.to_dict(),
        )
        counts["rankings"] += 1

    session.flush()
    return counts


def current_versions(session: Session) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(StdVersionRegistry).where(StdVersionRegistry.is_current.is_(True))
    ).all()
    return [
        {
            "artifact_type": r.artifact_type,
            "artifact_name": r.artifact_name,
            "version": r.version,
        }
        for r in rows
    ]
