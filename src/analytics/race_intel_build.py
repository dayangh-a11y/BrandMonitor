"""Persist Race Intelligence cards into anl_race_intelligence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.analytics.metrics import as_date, parse_race_class
from src.analytics.models import AnlRaceIntelligence
from src.analytics.race_intel import compute_race_intelligence
from src.warehouse.models import WhHorse, WhRace, WhRaceResult


def build_race_intelligence(
    session: Session,
    *,
    build_run_id: int | None = None,
    racecourse_code: str | None = None,
    race_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Rebuild Race Intelligence for warehouse races with official finishes."""
    if race_ids:
        session.execute(
            delete(AnlRaceIntelligence).where(AnlRaceIntelligence.race_id.in_(race_ids))
        )
    elif racecourse_code:
        session.execute(
            delete(AnlRaceIntelligence).where(
                AnlRaceIntelligence.racecourse_code == racecourse_code
            )
        )
    else:
        session.execute(delete(AnlRaceIntelligence))
    session.flush()

    horses = {h.id: h.name for h in session.scalars(select(WhHorse)).all()}
    q = select(WhRace)
    if racecourse_code:
        q = q.where(WhRace.racecourse_code == racecourse_code)
    if race_ids:
        q = q.where(WhRace.id.in_(race_ids))
    races = session.scalars(q).all()

    results_by_race: dict[int, list[WhRaceResult]] = {}
    target_ids = {r.id for r in races}
    rq = select(WhRaceResult)
    if target_ids:
        rq = rq.where(WhRaceResult.race_id.in_(target_ids))
    for res in session.scalars(rq).all():
        results_by_race.setdefault(res.race_id, []).append(res)

    now = datetime.now(timezone.utc)
    written = 0
    skipped = 0
    for race in races:
        runners = []
        for res in results_by_race.get(race.id, []):
            if res.finish_position is None or res.finish_position <= 0 or res.horse_id is None:
                continue
            runners.append(
                {
                    "horse_id": res.horse_id,
                    "horse_name": horses.get(res.horse_id, f"horse#{res.horse_id}"),
                    "finish": int(res.finish_position),
                    "rating": float(res.source_rating) if res.source_rating is not None else None,
                    "cloth": res.number,
                }
            )
        intel = compute_race_intelligence(
            race_id=race.id,
            runners=runners,
            race_class=parse_race_class(race.name),
        )
        if intel is None:
            skipped += 1
            continue
        session.add(
            AnlRaceIntelligence(
                race_id=race.id,
                race_date=as_date(race.race_date),
                racecourse_code=race.racecourse_code,
                race_name=race.name,
                breed=race.surface,
                difficulty_stars=intel.difficulty_stars,
                difficulty_label=intel.difficulty_label,
                crowd_accuracy_pct=intel.crowd_accuracy_pct,
                shock_score=intel.shock_score,
                prediction_confidence=intel.prediction_confidence,
                expectation_source=intel.expectation_source,
                biggest_surprise_horse=intel.biggest_surprise_horse,
                biggest_surprise_horse_id=intel.biggest_surprise_horse_id,
                most_overrated_horse=intel.most_overrated_horse,
                most_overrated_horse_id=intel.most_overrated_horse_id,
                most_underrated_horse=intel.most_underrated_horse,
                most_underrated_horse_id=intel.most_underrated_horse_id,
                favorite_name=intel.favorite_name,
                favorite_finish=intel.favorite_finish,
                winner_name=intel.winner_name,
                winner_expected_rank=intel.winner_expected_rank,
                field_size=intel.field_size,
                report_text=intel.as_report(),
                explain_json=intel.explain_json,
                runners_json=[
                    {
                        "horse_id": r.horse_id,
                        "horse_name": r.horse_name,
                        "finish": r.finish,
                        "rating": r.rating,
                        "expected_rank": r.expected_rank,
                        "residual": r.residual,
                    }
                    for r in intel.runners
                ],
                build_run_id=build_run_id,
                computed_at=now,
            )
        )
        written += 1

    session.flush()
    stats = {"written": written, "skipped": skipped}
    logger.info("Race intelligence build {}", stats)
    return stats


def get_race_intelligence_report(session: Session, race_id: int) -> str | None:
    row = session.scalar(
        select(AnlRaceIntelligence).where(AnlRaceIntelligence.race_id == race_id)
    )
    return row.report_text if row else None
