"""Load RunnerContext lists from warehouse + analytics metrics."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.analytics.metrics import as_date
from src.analytics.models import AnlHorseMetrics
from src.markets.scoring import RunnerContext
from src.warehouse.models import (
    WhHorse,
    WhJockey,
    WhRace,
    WhRaceResult,
    WhTrainer,
)


def load_field_for_race(
    session: Session,
    race_id: int,
    *,
    metrics_scope: str = "career",
) -> tuple[WhRace | None, list[RunnerContext]]:
    race = session.get(WhRace, race_id)
    if race is None:
        return None, []

    results = list(
        session.scalars(select(WhRaceResult).where(WhRaceResult.race_id == race_id)).all()
    )
    horse_ids = [r.horse_id for r in results if r.horse_id is not None]
    if horse_ids:
        horses = {
            h.id: h
            for h in session.scalars(select(WhHorse).where(WhHorse.id.in_(horse_ids))).all()
        }
    else:
        horses = {}
    jockeys = {j.id: j.name for j in session.scalars(select(WhJockey)).all()}
    trainers = {t.id: t.name for t in session.scalars(select(WhTrainer)).all()}

    metrics_rows = list(
        session.scalars(
            select(AnlHorseMetrics).where(
                AnlHorseMetrics.scope == metrics_scope,
                AnlHorseMetrics.breed == "*",
            )
        ).all()
    )
    # Prefer season_key='*' for career; for season take latest matching horse
    metrics_by_horse: dict[int, AnlHorseMetrics] = {}
    for m in metrics_rows:
        if metrics_scope == "career" and m.season_key != "*":
            continue
        prev = metrics_by_horse.get(m.horse_id)
        if prev is None or (m.starts or 0) >= (prev.starts or 0):
            metrics_by_horse[m.horse_id] = m

    # Rest days: last start before this race
    race_date = as_date(race.race_date)
    field: list[RunnerContext] = []
    for res in results:
        if res.horse_id is None:
            continue
        horse = horses.get(res.horse_id)
        if horse is None:
            continue
        m = metrics_by_horse.get(res.horse_id)
        # Rest days from prior starts
        rest_days = None
        if race_date is not None:
            prior_dates = session.execute(
                select(WhRace.race_date)
                .join(WhRaceResult, WhRaceResult.race_id == WhRace.id)
                .where(
                    WhRaceResult.horse_id == res.horse_id,
                    WhRace.race_date.is_not(None),
                    WhRace.id != race_id,
                )
                .order_by(WhRace.race_date.desc())
                .limit(8)
            ).all()
            for (pd,) in prior_dates:
                d = as_date(pd)
                if d is not None and d < race_date:
                    rest_days = (race_date - d).days
                    break

        ctx = RunnerContext(
            horse_id=horse.id,
            horse_name=horse.name,
            cloth=res.number,
            source_rating=float(res.source_rating) if res.source_rating is not None else None,
            odds=float(res.odds) if res.odds is not None else None,
            starts=int(m.starts) if m else 0,
            wins=int(m.wins) if m else 0,
            places=int(m.places) if m else 0,
            win_rate=m.win_rate if m else None,
            place_rate=m.place_rate if m else None,
            avg_finish=m.avg_finish if m else None,
            performance_rating=m.performance_rating if m else None,
            sex_adjusted_pr=m.sex_adjusted_performance_rating if m else None,
            form_score_5=m.form_score_5 if m else None,
            speed_index=m.speed_index if m else None,
            consistency_score=m.consistency_score if m else None,
            difficulty_index=m.difficulty_index if m else None,
            improvement_trend=m.improvement_trend if m else None,
            age_years=m.age_years if m else None,
            sex=m.sex_normalized if m else horse.sex,
            trainer=trainers.get(res.trainer_id) if res.trainer_id else None,
            jockey=jockeys.get(res.jockey_id) if res.jockey_id else None,
            weight=float(res.weight) if res.weight is not None else None,
            rest_days=rest_days,
            meta={
                "distance_pref_score": m.distance_preference_score if m else None,
                "track_pref_score": m.track_preference_score if m else None,
                "trainer_score": m.trainer_combination_score if m else None,
                "jockey_score": m.jockey_combination_score if m else None,
                "field_strength": m.difficulty_index if m else None,
                "distance_pref": m.distance_preference if m else None,
                "track_pref": m.track_preference if m else None,
            },
        )
        field.append(ctx)
    return race, field


def load_runner_by_horse_id(
    session: Session,
    horse_id: int,
    *,
    metrics_scope: str = "career",
) -> RunnerContext | None:
    horse = session.get(WhHorse, horse_id)
    if horse is None:
        return None
    m = session.scalar(
        select(AnlHorseMetrics)
        .where(
            AnlHorseMetrics.horse_id == horse_id,
            AnlHorseMetrics.scope == metrics_scope,
            AnlHorseMetrics.breed == "*",
        )
        .order_by(AnlHorseMetrics.starts.desc())
        .limit(1)
    )
    return RunnerContext(
        horse_id=horse.id,
        horse_name=horse.name,
        source_rating=None,
        starts=int(m.starts) if m else 0,
        wins=int(m.wins) if m else 0,
        places=int(m.places) if m else 0,
        win_rate=m.win_rate if m else None,
        place_rate=m.place_rate if m else None,
        avg_finish=m.avg_finish if m else None,
        performance_rating=m.performance_rating if m else None,
        sex_adjusted_pr=m.sex_adjusted_performance_rating if m else None,
        form_score_5=m.form_score_5 if m else None,
        speed_index=m.speed_index if m else None,
        consistency_score=m.consistency_score if m else None,
        difficulty_index=m.difficulty_index if m else None,
        improvement_trend=m.improvement_trend if m else None,
        age_years=m.age_years if m else None,
        sex=m.sex_normalized if m else horse.sex,
        meta={
            "distance_pref_score": m.distance_preference_score if m else None,
            "track_pref_score": m.track_preference_score if m else None,
            "trainer_score": m.trainer_combination_score if m else None,
            "jockey_score": m.jockey_combination_score if m else None,
            "field_strength": m.difficulty_index if m else None,
        },
    )
