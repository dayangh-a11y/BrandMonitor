"""Virtual Race Engine — hypothetical fields, no race_id required."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.analytics.models import AnlHorseMetrics
from src.markets.h2h import analyze_h2h_market
from src.prerace.horse_score import build_horse_scores
from src.prerace.race_score import score_race_context
from src.prerace.reports import generate_reports
from src.prerace.types import ValidationIssue
from src.prerace.validate import validate_prerace, validation_blocks_publish
from src.virtual_race.field import build_virtual_field, resolve_racecourse_code
from src.virtual_race.models import AnlVirtualRaceReport
from src.virtual_race.report import format_virtual_race_report
from src.virtual_race.scenario import VirtualRaceScenario, scenario_from_dict


def _enrich_fatigue(session: Session, field) -> None:
    ids = [r.horse_id for r in field]
    if not ids:
        return
    rows = session.scalars(
        select(AnlHorseMetrics).where(
            AnlHorseMetrics.horse_id.in_(ids),
            AnlHorseMetrics.scope == "career",
            AnlHorseMetrics.breed == "*",
        )
    ).all()
    by = {m.horse_id: m for m in rows}
    for r in field:
        m = by.get(r.horse_id)
        if m is None:
            continue
        if m.fatigue_score is not None:
            r.meta["fatigue_score"] = m.fatigue_score
        if m.weather_preference_score is not None:
            r.meta["weather_pref_score"] = m.weather_preference_score


def _field_risk_and_confidence(horses: list) -> dict[str, Any]:
    if not horses:
        return {
            "field_risk_score": None,
            "field_confidence": "Low",
            "field_confidence_score": 0.0,
            "mean_sample_size": 0,
        }
    risks = [h.risk_score for h in horses if h.risk_score is not None]
    confs = [h.confidence_score for h in horses]
    samples = [h.sample_size for h in horses]
    mean_conf = sum(confs) / len(confs) if confs else 0.0
    band = "High" if mean_conf >= 70 else "Medium" if mean_conf >= 45 else "Low"
    return {
        "field_risk_score": round(sum(risks) / len(risks), 3) if risks else None,
        "field_confidence": band,
        "field_confidence_score": round(mean_conf, 2),
        "mean_sample_size": round(sum(samples) / len(samples), 2) if samples else 0,
    }


def _flatten_pairwise(h2h_matrix: Any) -> list[dict[str, Any]]:
    if not h2h_matrix:
        return []
    if isinstance(h2h_matrix, list):
        return list(h2h_matrix)
    if isinstance(h2h_matrix, dict):
        out: list[dict[str, Any]] = []
        for a, row in h2h_matrix.items():
            if not isinstance(row, dict):
                continue
            for b, vals in row.items():
                item = {"a": a, "b": b}
                if isinstance(vals, dict):
                    item.update(vals)
                else:
                    item["p_a_ahead"] = vals
                out.append(item)
        return out
    return []


def build_virtual_race_report(
    session: Session,
    scenario: VirtualRaceScenario | dict[str, Any],
    *,
    persist: bool = False,
    include_h2h: bool = True,
    scenario_key: str | None = None,
) -> dict[str, Any]:
    """
    Score a hypothetical race without any wh_races / race_id.

    ``persist`` defaults to False — nothing is saved unless requested.
    """
    if isinstance(scenario, dict):
        scenario = scenario_from_dict(scenario)

    field, resolution = build_virtual_field(session, scenario)
    _enrich_fatigue(session, field)

    course_code = resolve_racecourse_code(scenario)
    weather = scenario.weather_dict()
    unresolved = [r for r in resolution if r.get("status") != "ok"]

    if not field:
        return {
            "status": "blocked",
            "publishable": False,
            "virtual": True,
            "race_id": None,
            "version": "1.0.0",
            "scenario": scenario.to_dict(),
            "resolution": resolution,
            "validation": [
                {
                    "code": "empty_virtual_field",
                    "severity": "error",
                    "message": "No runners resolved — cannot invent predictions",
                }
            ],
            "reports": {},
            "horses": [],
            "pairwise": [],
            "value_horses": None,
            "dark_horse": None,
            "risk": {"field_risk_score": None, "per_horse": []},
            "confidence": {
                "field_confidence": "Low",
                "field_confidence_score": 0.0,
                "mean_sample_size": 0,
                "per_horse": [],
            },
            "report_text": "INSUFFICIENT DATA — virtual field empty (no resolved horses)",
        }

    race_ctx = score_race_context(
        field,
        distance=scenario.distance,
        race_class=scenario.race_class,
        weather=weather,
        classification_difficulty=None,
    )

    h2h_matrix = None
    pairwise: list[dict[str, Any]] = []
    if include_h2h and len(field) >= 2:
        h2h_ans = analyze_h2h_market(
            field,
            session=session,
            race_distance=scenario.distance,
            race_track=course_code,
        )
        if isinstance(h2h_ans.prediction, dict):
            h2h_matrix = h2h_ans.prediction.get("matrix")
            pairwise = _flatten_pairwise(h2h_matrix)

    horses = build_horse_scores(
        field,
        race_distance=scenario.distance,
        weather=weather,
        field_competition=race_ctx.competition_level,
        h2h_matrix=h2h_matrix,
    )
    reports = generate_reports(horses, field)
    base_issues = validate_prerace(field, horses)
    issues: list[ValidationIssue] = list(base_issues)
    for u in unresolved:
        issues.append(
            ValidationIssue(
                code="unresolved_runner",
                severity="warning",
                message=f"Could not resolve runner {u.get('entry')}",
            )
        )
    blocked = validation_blocks_publish(base_issues) or not field
    field_meta = _field_risk_and_confidence(horses)

    payload: dict[str, Any] = {
        "status": "blocked" if blocked else "ok",
        "publishable": not blocked,
        "virtual": True,
        "race_id": None,
        "version": "1.0.0",
        "scenario_key": scenario_key,
        "race": {
            "race_id": None,
            "virtual": True,
            "race_date": str(scenario.date) if scenario.date else None,
            "racecourse_code": course_code,
            "racecourse": scenario.racecourse,
            "race_name": scenario.race_name or "Virtual Race",
            "distance": scenario.distance,
            "class_code": scenario.race_class,
            "track": scenario.track,
            "track_condition": scenario.track_condition,
            "field_size": len(field),
            "entered": len(scenario.horses),
            "resolved": len(field),
            "unresolved": len(unresolved),
        },
        "scenario": scenario.to_dict(),
        "resolution": resolution,
        "race_context": race_ctx.to_dict(),
        "horses": [h.to_dict() for h in horses],
        "reports": reports,
        "pairwise": pairwise,
        "value_horses": reports.get("best_value_horse"),
        "dark_horse": reports.get("dark_horse"),
        "risk": {
            "field_risk_score": field_meta["field_risk_score"],
            "per_horse": [
                {
                    "horse_id": h.horse_id,
                    "horse": h.horse_name,
                    "risk_score": h.risk_score,
                }
                for h in horses
            ],
        },
        "confidence": {
            "field_confidence": field_meta["field_confidence"],
            "field_confidence_score": field_meta["field_confidence_score"],
            "mean_sample_size": field_meta["mean_sample_size"],
            "per_horse": [
                {
                    "horse_id": h.horse_id,
                    "horse": h.horse_name,
                    "confidence": h.confidence,
                    "confidence_score": h.confidence_score,
                    "sample_size": h.sample_size,
                    "data_quality": h.data_quality,
                }
                for h in horses
            ],
        },
        "validation": [i.to_dict() for i in issues],
        "h2h_pairs": len(pairwise),
    }
    payload["report_text"] = format_virtual_race_report(payload)

    if persist and not blocked:
        key = scenario_key or f"vr-{uuid4().hex[:12]}"
        payload["scenario_key"] = key
        session.add(
            AnlVirtualRaceReport(
                scenario_key=key,
                race_date=str(scenario.date) if scenario.date else None,
                racecourse_code=course_code,
                race_name=scenario.race_name or "Virtual Race",
                distance=scenario.distance,
                race_class=scenario.race_class,
                scenario_json=scenario.to_dict(),
                race_context_json=payload["race_context"],
                horses_json=payload["horses"],
                reports_json=reports,
                pairwise_json=pairwise,
                validation_json=payload["validation"],
                resolution_json=resolution,
                report_text=payload["report_text"],
                publishable=1,
                version="1.0.0",
            )
        )
        session.flush()
        logger.info("Virtual race report saved key={} horses={}", key, len(horses))
    elif blocked:
        logger.warning(
            "Virtual race blocked unresolved={} field={}", len(unresolved), len(field)
        )

    return payload
