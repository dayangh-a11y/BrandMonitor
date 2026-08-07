"""Build a temporary RunnerContext field for a virtual race (no race_id)."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.identity import HorseQuery, resolve_horse
from src.identity.resolve import warehouse_ids_for_horse
from src.markets.context import load_runner_by_horse_id
from src.markets.scoring import RunnerContext
from src.racecourses.registry import resolve_racecourse
from src.virtual_race.scenario import VirtualHorseEntry, VirtualRaceScenario
from src.warehouse.models import WhRace, WhRaceResult


def resolve_racecourse_code(scenario: VirtualRaceScenario) -> str | None:
    if scenario.racecourse_code:
        return scenario.racecourse_code
    if scenario.racecourse:
        course = resolve_racecourse(scenario.racecourse)
        if course:
            return course.code
    return None


def _rest_days(session: Session, warehouse_horse_id: int, as_of: date | None) -> int | None:
    if as_of is None:
        return None
    prior = session.execute(
        select(WhRace.race_date)
        .join(WhRaceResult, WhRaceResult.race_id == WhRace.id)
        .where(
            WhRaceResult.horse_id == warehouse_horse_id,
            WhRace.race_date.is_not(None),
        )
        .order_by(WhRace.race_date.desc())
        .limit(12)
    ).all()
    for (pd,) in prior:
        if pd is None:
            continue
        d = pd if isinstance(pd, date) else date.fromisoformat(str(pd)[:10])
        if d < as_of:
            return (as_of - d).days
    return None


def _resolve_warehouse_id(session: Session, entry: VirtualHorseEntry) -> tuple[int | None, dict[str, Any]]:
    """Map entry → warehouse horse id using IDs or Identity Engine."""
    evidence: dict[str, Any] = {}
    if entry.horse_id is not None:
        evidence["method"] = "warehouse_horse_id"
        return int(entry.horse_id), evidence

    if entry.permanent_horse_id is not None:
        wh_ids = warehouse_ids_for_horse(session, int(entry.permanent_horse_id))
        evidence["method"] = "permanent_horse_id"
        evidence["permanent_horse_id"] = entry.permanent_horse_id
        evidence["warehouse_ids"] = wh_ids
        return (wh_ids[0] if wh_ids else None), evidence

    hits = resolve_horse(
        session,
        HorseQuery(
            name=entry.name,
            sire=entry.sire,
            dam=entry.dam,
            age=entry.age,
            sex=entry.sex,
            owner=entry.owner,
            trainer=entry.trainer,
            source_horse_id=entry.source_horse_id,
        ),
        limit=1,
    )
    if not hits:
        evidence["method"] = "unresolved"
        evidence["name"] = entry.name
        return None, evidence
    hit = hits[0]
    evidence["method"] = "identity_resolve"
    evidence["horse_id"] = hit.horse_id
    evidence["score"] = hit.score
    evidence["decision"] = hit.decision
    if hit.warehouse_horse_id:
        return hit.warehouse_horse_id, evidence
    wh_ids = warehouse_ids_for_horse(session, hit.horse_id)
    evidence["warehouse_ids"] = wh_ids
    return (wh_ids[0] if wh_ids else None), evidence


def build_virtual_field(
    session: Session,
    scenario: VirtualRaceScenario,
    *,
    metrics_scope: str = "career",
) -> tuple[list[RunnerContext], list[dict[str, Any]]]:
    """
    Assemble a temporary field from a hypothetical card.

    Returns (field, resolution_log). Unresolved runners are logged and skipped.
    """
    as_of = scenario.as_of_date()
    field: list[RunnerContext] = []
    log: list[dict[str, Any]] = []

    for idx, entry in enumerate(scenario.horses):
        wh_id, evidence = _resolve_warehouse_id(session, entry)
        row_log: dict[str, Any] = {
            "index": idx,
            "entry": entry.to_dict(),
            "warehouse_horse_id": wh_id,
            **evidence,
        }
        if wh_id is None:
            row_log["status"] = "unresolved"
            log.append(row_log)
            continue

        runner = load_runner_by_horse_id(session, wh_id, metrics_scope=metrics_scope)
        if runner is None:
            row_log["status"] = "no_warehouse_row"
            log.append(row_log)
            continue

        # Overlay hypothetical card attributes
        cloth = entry.cloth if entry.cloth is not None else entry.draw
        if cloth is not None:
            runner.cloth = int(cloth)
        elif runner.cloth is None:
            runner.cloth = idx + 1
        if entry.weight is not None:
            runner.weight = float(entry.weight)
        if entry.jockey:
            runner.jockey = entry.jockey
        if entry.trainer:
            runner.trainer = entry.trainer
        if entry.rating is not None:
            runner.source_rating = float(entry.rating)
        if entry.odds is not None:
            runner.odds = float(entry.odds)
        if entry.age is not None and runner.age_years is None:
            runner.age_years = float(entry.age)
        if entry.sex and not runner.sex:
            runner.sex = entry.sex

        rest = _rest_days(session, wh_id, as_of)
        if rest is not None:
            runner.rest_days = rest

        runner.meta = dict(runner.meta or {})
        runner.meta["virtual"] = True
        runner.meta["resolution"] = evidence
        if entry.draw is not None:
            runner.meta["draw"] = entry.draw
        if entry.owner:
            runner.meta["owner"] = entry.owner

        row_log["status"] = "ok"
        row_log["resolved_name"] = runner.horse_name
        log.append(row_log)
        field.append(runner)

    return field, log
