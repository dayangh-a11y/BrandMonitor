"""Orchestrate a complete pre-race intelligence report."""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.markets.context import load_field_for_race
from src.markets.h2h import analyze_h2h_market
from src.prerace.horse_score import build_horse_scores
from src.prerace.models import AnlPreraceReport
from src.prerace.race_score import score_race_context
from src.prerace.report import format_prerace_report
from src.prerace.reports import generate_reports
from src.prerace.validate import validate_prerace, validation_blocks_publish
from src.standardization.models import StdRaceClassification
from src.warehouse.models import WhRace, WhRaceWeather


def _weather_dict(session: Session, race_id: int) -> dict[str, Any] | None:
    wx = session.scalar(select(WhRaceWeather).where(WhRaceWeather.race_id == race_id))
    if wx is None:
        return None
    return {
        "rainfall_mm": wx.rainfall_mm,
        "rainfall_day_mm": wx.rainfall_day_mm,
        "wind_speed_kmh": wx.wind_speed_kmh,
        "visibility_m": wx.visibility_m,
        "weather_condition": wx.weather_condition,
        "track_condition": wx.track_condition,
        "air_temperature_c": wx.air_temperature_c,
        "humidity_pct": wx.humidity_pct,
    }


def _enrich_fatigue(session: Session, field) -> None:
    """Attach fatigue_score from anl_horse_metrics into runner meta if present."""
    from src.analytics.models import AnlHorseMetrics

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


def build_prerace_report(
    session: Session,
    race_id: int,
    *,
    persist: bool = True,
    include_h2h: bool = True,
) -> dict[str, Any]:
    """
    Produce a complete pre-race intelligence report for one race card.

    Never fabricates predictions when validation hard-blocks (empty field).
    Low confidence is warned, not invented away.
    """
    race, field = load_field_for_race(session, race_id)
    if race is None:
        return {
            "race_id": race_id,
            "status": "error",
            "publishable": False,
            "validation": [
                {"code": "race_not_found", "severity": "error", "message": f"No race {race_id}"}
            ],
            "report_text": f"INSUFFICIENT DATA — race {race_id} not found",
        }

    _enrich_fatigue(session, field)
    weather = _weather_dict(session, race_id)
    classification = session.scalar(
        select(StdRaceClassification).where(StdRaceClassification.race_id == race_id)
    )
    class_diff = classification.difficulty if classification else None
    class_code = classification.class_code if classification else None

    race_ctx = score_race_context(
        field,
        distance=race.distance,
        race_class=class_code,
        weather=weather,
        classification_difficulty=class_diff,
    )

    h2h_matrix = None
    if include_h2h and len(field) >= 2:
        h2h_ans = analyze_h2h_market(
            field,
            session=session,
            race_distance=race.distance,
            race_track=race.racecourse_code,
        )
        if isinstance(h2h_ans.prediction, dict):
            h2h_matrix = h2h_ans.prediction.get("matrix")

    horses = build_horse_scores(
        field,
        race_distance=race.distance,
        weather=weather,
        field_competition=race_ctx.competition_level,
        h2h_matrix=h2h_matrix,
    )
    reports = generate_reports(horses, field)
    issues = validate_prerace(field, horses)
    blocked = validation_blocks_publish(issues) or not field

    payload = {
        "status": "blocked" if blocked else "ok",
        "publishable": not blocked,
        "version": "1.0.0",
        "race": {
            "race_id": race.id,
            "race_date": str(race.race_date) if race.race_date else None,
            "racecourse_code": race.racecourse_code,
            "race_name": race.name,
            "distance": race.distance,
            "class_code": class_code,
            "field_size": len(field),
        },
        "race_context": race_ctx.to_dict(),
        "horses": [h.to_dict() for h in horses],
        "reports": reports,
        "validation": [i.to_dict() for i in issues],
        "h2h_pairs": len(h2h_matrix or []),
    }
    payload["report_text"] = format_prerace_report(payload)

    if persist and not blocked:
        session.execute(delete(AnlPreraceReport).where(AnlPreraceReport.race_id == race_id))
        session.add(
            AnlPreraceReport(
                race_id=race_id,
                race_date=str(race.race_date) if race.race_date else None,
                racecourse_code=race.racecourse_code,
                race_name=race.name,
                race_context_json=payload["race_context"],
                horses_json=payload["horses"],
                reports_json=reports,
                validation_json=payload["validation"],
                publishable=1,
                report_text=payload["report_text"],
                version="1.0.0",
            )
        )
        session.flush()
        logger.info("Pre-race report saved race_id={} horses={}", race_id, len(horses))
    elif blocked:
        logger.warning("Pre-race report blocked race_id={} issues={}", race_id, len(issues))

    return payload


def build_prerace_for_card_day(
    session: Session,
    *,
    race_date: str | None = None,
    racecourse_code: str | None = None,
    limit: int | None = 20,
) -> dict[str, Any]:
    """Build reports for a race-card day (next week / any date)."""
    from datetime import date as date_cls

    q = select(WhRace)
    if racecourse_code:
        q = q.where(WhRace.racecourse_code == racecourse_code)
    if race_date:
        q = q.where(WhRace.race_date == date_cls.fromisoformat(race_date))
    else:
        latest_q = select(WhRace.race_date).order_by(WhRace.race_date.desc()).limit(1)
        if racecourse_code:
            latest_q = latest_q.where(WhRace.racecourse_code == racecourse_code)
        latest = session.scalar(latest_q)
        if latest is None:
            return {"races": 0, "reports": []}
        q = q.where(WhRace.race_date == latest)

    q = q.order_by(WhRace.race_number.asc(), WhRace.id.asc())
    if limit:
        q = q.limit(limit)
    races = list(session.scalars(q).all())
    reports = []
    for race in races:
        reports.append(build_prerace_report(session, race.id, persist=True))
    return {
        "races": len(reports),
        "race_date": str(races[0].race_date) if races else None,
        "reports": reports,
    }
