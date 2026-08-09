"""Feature recalculation framework — clears/rebuilds empty feature shells."""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.features.models import (
    FeatHorseFeatures,
    FeatJockeyFeatures,
    FeatRaceFeatures,
    FeatRecalcRun,
    FeatTrainerFeatures,
)
from src.warehouse.models import WhHorse, WhJockey, WhRace, WhTrainer


def recalculate_all_features(session: Session) -> FeatRecalcRun:
    """
    Recreate empty feature rows for every warehouse entity.

    No statistics are computed here — only infrastructure scaffolding so
    future feature builders can fill `features_json` safely and repeatedly.
    """
    run = FeatRecalcRun(status="running")
    session.add(run)
    session.flush()

    session.execute(delete(FeatHorseFeatures))
    session.execute(delete(FeatRaceFeatures))
    session.execute(delete(FeatTrainerFeatures))
    session.execute(delete(FeatJockeyFeatures))
    session.flush()

    now = datetime.now(timezone.utc)
    touched = 0
    for horse_id in session.scalars(select(WhHorse.id)):
        session.add(
            FeatHorseFeatures(
                horse_id=horse_id,
                features_json={},
                feature_version="0",
                computed_at=now,
                pipeline_run_id=run.id,
            )
        )
        touched += 1
    from src.racecourses.features import merge_track_config_into_features

    for race in session.scalars(select(WhRace)):
        race_feats = merge_track_config_into_features(
            {},
            racecourse_code=race.racecourse_code,
            track_name=race.track,
            city=race.track,
        )
        session.add(
            FeatRaceFeatures(
                race_id=race.id,
                features_json=race_feats,
                feature_version="0.1-track-config",
                computed_at=now,
                pipeline_run_id=run.id,
            )
        )
        touched += 1
    for trainer_id in session.scalars(select(WhTrainer.id)):
        session.add(
            FeatTrainerFeatures(
                trainer_id=trainer_id,
                features_json={},
                feature_version="0",
                computed_at=now,
                pipeline_run_id=run.id,
            )
        )
        touched += 1
    for jockey_id in session.scalars(select(WhJockey.id)):
        session.add(
            FeatJockeyFeatures(
                jockey_id=jockey_id,
                features_json={},
                feature_version="0",
                computed_at=now,
                pipeline_run_id=run.id,
            )
        )
        touched += 1

    run.rows_touched = touched
    run.status = "success"
    run.finished_at = datetime.now(timezone.utc)
    session.flush()
    logger.info("Feature recalc complete rows={}", touched)
    return run
